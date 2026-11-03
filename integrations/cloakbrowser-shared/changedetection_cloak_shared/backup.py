"""Offline cold backup/restore of a stopped CloakBrowser Profile.

No live BrowserManager requests. Call only after stopping the main container.
Do not run another container pointing to the Profile simultaneously.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path

from .profile_manager import ProfileLock


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_safe_profile(profile):
    raw_profile = Path(profile)
    if raw_profile.is_symlink():
        raise ValueError('Profile may not be a symlink')
    profile = raw_profile.resolve()
    if profile == Path('/') or not profile.is_dir():
        raise ValueError(f'Profile must be an existing directory, got {profile}')
    return profile


def _validate_profile_tree(profile):
    # Never archive dangerous links; no backup should escape the Profile root.
    for path in profile.rglob('*'):
        if path.is_symlink() and path.name.startswith('Singleton'):
            continue  # Chromium's stale singleton symlink is not profile data.
        if path.is_symlink():
            raise ValueError(f'Symlink in Profile, refusing unsafe archive: {path}')
        if not (path.is_file() or path.is_dir()):
            raise ValueError(f'Unsupported special Profile item: {path}')


def backup(profile_dir, output_dir):
    profile = _is_safe_profile(profile_dir)
    output = Path(output_dir).resolve()
    if profile == output or profile in output.parents or output in profile.parents:
        raise ValueError('Backup directory must be outside the Profile tree')
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    with ProfileLock(profile):
        _validate_profile_tree(profile)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        destination = output / f'cloakbrowser-profile-{stamp}.tar.gz'
        if destination.exists():
            raise FileExistsError(destination)
        fd, temp_name = tempfile.mkstemp(prefix='.cloakbrowser-backup-', suffix='.tmp', dir=output)
        os.close(fd)
        temp = Path(temp_name)
        try:
            os.chmod(temp, 0o600)
            with tarfile.open(temp, 'w:gz') as archive:
                def filtered(info):
                    if info.name.endswith('/.changedetection.lock') or info.name.endswith('/SingletonLock') or info.name.endswith('/SingletonSocket') or info.name.endswith('/SingletonCookie'):
                        return None
                    return info
                archive.add(profile, arcname='profile', recursive=True, filter=filtered)
                metadata = {
                    'schema_version': 1,
                    'backup_type': 'cold',
                    'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'profile_name': profile.name,
                }
                import io
                data = json.dumps(metadata, sort_keys=True).encode('utf-8')
                info = tarfile.TarInfo('metadata.json')
                info.size = len(data)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(data))
            # Flush before publishing the archive.
            with open(temp, 'rb') as fp:
                os.fsync(fp.fileno())
            os.replace(temp, destination)
            checksum_path = destination.with_name(destination.name + '.sha256')
            checksum_path.write_text(f'{_sha256(destination)}  {destination.name}\n', encoding='ascii')
            os.chmod(checksum_path, 0o600)
            return destination, checksum_path
        finally:
            temp.unlink(missing_ok=True)


def _safe_members(tar):
    members = tar.getmembers()
    total = 0
    seen = set()
    for m in members:
        path = Path(m.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ('profile', 'metadata.json'):
            raise ValueError(f'Invalid backup entry: {m.name}')
        if path.parts[0] == 'metadata.json' and len(path.parts) != 1:
            raise ValueError(f'Unexpected metadata subpath: {m.name}')
        key = str(path)
        if key in seen:
            raise ValueError(f'Duplicate backup entry: {m.name}')
        seen.add(key)
        if m.issym() or m.islnk() or not (m.isdir() or m.isfile()):
            raise ValueError(f'Unsupported backup entry: {m.name}')
        if m.name == 'metadata.json' and not m.isfile():
            raise ValueError('Invalid metadata entry')
        total += m.size
        if total > 20 * 1024 ** 3:
            raise ValueError('Backup uncompressed size exceeds 20 GiB safety limit')
    if not any(m.name.rstrip('/') == 'profile' and m.isdir() for m in members):
        raise ValueError('Missing profile directory in archive')
    return members


def restore(profile_dir, archive_path, expected_sha256):
    raw_profile = Path(profile_dir)
    if raw_profile.is_symlink():
        raise ValueError('Refusing to restore to a symlink Profile')
    profile = raw_profile.resolve()
    if profile == Path('/'):
        raise ValueError('Refusing to restore to filesystem root')
    if profile.exists() and not profile.is_dir():
        raise ValueError('Restore destination must be a directory')
    archive_path = Path(archive_path).resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    digest = _sha256(archive_path)
    if digest.lower() != expected_sha256.lower():
        raise ValueError('Backup SHA-256 mismatch')
    # Prevent recovery from placing archives/staging inside the destination.
    if archive_path == profile or profile in archive_path.parents:
        raise ValueError('Backup archive must be outside the Profile directory')
    profile.parent.mkdir(parents=True, exist_ok=True)
    with ProfileLock(profile):
        # Only restore into an empty/nonexistent directory; never overwrite
        # existing login data. Operator must move the current Profile aside.
        existing = [p for p in profile.iterdir() if p.name == '.changedetection.lock' or p.name.startswith('Singleton')]
        unexpected = [p for p in profile.iterdir() if p not in existing]
        if unexpected:
            raise FileExistsError(f'Profile is not empty; manually preserve it before restore: {profile}')
        with tempfile.TemporaryDirectory(prefix='.cloakbrowser-restore-', dir=profile.parent) as staging:
            staging_path = Path(staging)
            with tarfile.open(archive_path, 'r:gz') as tar:
                members = _safe_members(tar)
                # Extract each file explicitly: no symlink, hardlink, or device
                # may be materialized, even on Python without tar filters.
                for member in members:
                    target = staging_path / member.name
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        src = tar.extractfile(member)
                        if src is None:
                            raise ValueError(f'Cannot read {member.name}')
                        with src, open(target, 'xb') as dst:
                            import shutil
                            shutil.copyfileobj(src, dst)
                        os.chmod(target, member.mode & 0o600)
            restored = staging_path / 'profile'
            # Refuse a backup containing nested unexpected metadata or duplicate
            # paths before altering the bind-mounted destination Profile.
            if not restored.is_dir():
                raise ValueError('Extracted archive has no Profile directory')
            # Profile may be a Docker bind mount and cannot be atomically
            # replaced. Copy only after complete validation/extraction.
            import shutil
            copied = []
            try:
                for child in restored.iterdir():
                    destination = profile / child.name
                    if destination.exists():
                        raise FileExistsError(destination)
                    # Record the destination BEFORE copytree/copy2 so that
                    # an interrupted copy is included in rollback.
                    copied.append(destination)
                    if child.is_dir():
                        shutil.copytree(child, destination, symlinks=False)
                        for root, dirs, files in os.walk(destination):
                            os.chmod(root, 0o700)
                            for name in files:
                                os.chmod(Path(root) / name, 0o600)
                    else:
                        shutil.copy2(child, destination)
                        os.chmod(destination, 0o600)
                os.chmod(profile, 0o700)
            except Exception:
                # Remove only files created by this restore, never preexisting
                # user profile files or Chromium's lock file.
                for child in reversed(copied):
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
                raise
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=os.getenv('CLOAKBROWSER_PROFILE_DIR', '/browser-profile'))
    sub = parser.add_subparsers(dest='command', required=True)
    cmd_backup = sub.add_parser('backup', help='Cold backup: app must be stopped')
    cmd_backup.add_argument('--output', required=True)
    cmd_restore = sub.add_parser('restore', help='Restore only into empty Profile')
    cmd_restore.add_argument('--archive', required=True)
    cmd_restore.add_argument('--sha256', required=True, help='Expected independent checksum')
    args = parser.parse_args()
    if args.command == 'backup':
        archive, checksum = backup(args.profile, args.output)
        print(f'Backup: {archive}\nChecksum: {checksum}')
    else:
        restored = restore(args.profile, args.archive, args.sha256)
        print(f'Restored: {restored}')


if __name__ == '__main__':
    main()
