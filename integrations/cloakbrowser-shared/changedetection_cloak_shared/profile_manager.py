"""Advisory flock for a single persistent Chromium Profile (Linux Docker only)."""
import fcntl
import os
from pathlib import Path


class ProfileLock:
    """Lock lives alongside, not inside, the Chrome Profile.

    Every runtime or backup tool cooperating with this code must acquire it.
    Chromium also has its own profile lock; do not remove Chromium Singleton*
    files manually, or force a second instance onto the same Profile.
    """
    def __init__(self, profile_dir):
        self.profile_dir = Path(profile_dir).resolve()
        self.lock_path = self.profile_dir / '.changedetection.lock'
        self._fd = None

    def acquire(self):
        if self._fd is not None:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise RuntimeError(f'Profile is in use by another managed process: {self.profile_dir}') from exc
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def release(self):
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()
