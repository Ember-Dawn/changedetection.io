"""Local regression tests for post-round-3 reliability hardening (no Chromium)."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import loguru
except ImportError:
    import types
    sys.modules['loguru'] = types.SimpleNamespace(logger=types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manager import BrowserManager, _ManagedPage
from changedetection_cloak_shared.backup import backup, restore, _sha256
from changedetection_cloak_shared.profile_manager import ProfileLock


class SlowClosePage:
    def __init__(self):
        self.closed = False
        self.finish = asyncio.Event()

    def is_closed(self):
        return self.closed

    async def close(self):
        await self.finish.wait()
        self.closed = True


class PageTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_cancel_keeps_background_cleanup_and_quota(self):
        manager = BrowserManager()
        manager._semaphore = asyncio.Semaphore(1)
        await manager._semaphore.acquire()
        original = SlowClosePage()
        page = _ManagedPage(original, manager._semaphore, manager, manager._generation)
        worker = asyncio.create_task(page.close())
        await asyncio.sleep(0)
        worker.cancel()
        # Finish before the cancellation cleanup grace period expires.
        original.finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await worker
        await asyncio.sleep(0)
        self.assertEqual(manager._semaphore._value, 1)
        self.assertNotIn(page, manager._live_pages)
        await page.close()
        self.assertEqual(manager._semaphore._value, 1)

    async def test_preview_task_is_accounted_for(self):
        manager = BrowserManager()
        async def operation():
            await asyncio.sleep(0.02)
            return 'ok'
        try:
            answer = await asyncio.to_thread(manager.call_sync, operation())
            self.assertEqual(answer, 'ok')
            self.assertEqual(manager.status()['preview_operations'], 0)
        finally:
            manager.stop()

    async def test_quick_run_does_not_leave_registration(self):
        manager = BrowserManager()
        async def noop():
            return 'finished'
        try:
            self.assertEqual(await manager.run_fetch('quick', noop), 'finished')
            # callback may execute on the manager loop after worker is notified
            await asyncio.sleep(0.02)
            self.assertEqual(manager.status()['active_jobs'], 0)
        finally:
            manager.stop()


class RestoreTests(unittest.TestCase):
    def test_restore_rolls_back_partial_directory_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'
            (source/'Default').mkdir(parents=True)
            (source/'Default'/'Cookies').write_bytes(b'session')
            archive, _ = backup(source, root/'backups')
            target = root/'target'
            target.mkdir()
            import shutil
            original = shutil.copytree
            def copy_and_fail(src, dst, **kwargs):
                original(src, dst, **kwargs)
                raise OSError('simulated interrupted copy')
            with patch('shutil.copytree', side_effect=copy_and_fail):
                with self.assertRaises(OSError):
                    restore(target, archive, _sha256(archive))
            self.assertFalse((target/'Default').exists())

    def test_profile_lock_symlink_rejected(self):
        if not hasattr(os, 'symlink'):
            self.skipTest('OS lacks symlink')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root/'actual'
            target.mkdir()
            (root/'linked').symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                ProfileLock(root/'linked')
            (target/'.changedetection.lock').symlink_to(root/'linked-lock-target')
            with self.assertRaises(OSError):
                ProfileLock(target).acquire()


if __name__ == '__main__':
    unittest.main()
