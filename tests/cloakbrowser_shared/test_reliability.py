"""Local, Chromium-free unit checks for round three invariants."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import loguru
except ImportError:
    import types
    sys.modules['loguru'] = types.SimpleNamespace(logger=types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manager import BrowserManager, _ManagedPage
from changedetection_cloak_shared.profile_manager import ProfileLock
from changedetection_cloak_shared.backup import backup, restore, _sha256


class FailingPage:
    def is_closed(self):
        return False

    async def close(self):
        raise TimeoutError('renderer unresponsive')


class PageSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_close_keeps_page_quota_and_invalidates_context(self):
        manager = BrowserManager()
        manager._semaphore = asyncio.Semaphore(1)
        page = _ManagedPage(FailingPage(), manager._semaphore, manager, manager._generation)
        await manager._semaphore.acquire()
        with self.assertRaises(TimeoutError):
            await page.close()
        self.assertEqual(manager._semaphore._value, 0)
        self.assertTrue(manager._unhealthy)

    async def test_stop_does_not_start_browser(self):
        manager = BrowserManager()
        manager.stop()
        with self.assertRaises(RuntimeError):
            manager.submit(asyncio.sleep(0))


class ProfileTests(unittest.TestCase):
    def test_only_one_lock_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            one, two = ProfileLock(tmp), ProfileLock(tmp)
            one.acquire()
            with self.assertRaises(RuntimeError):
                two.acquire()
            one.release()
            two.acquire()
            two.release()

    def test_cold_backup_and_empty_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src, dest, store = base/'src', base/'restored', base/'backup'
            src.mkdir()
            (src/'Default').mkdir()
            (src/'Default'/'Cookies').write_bytes(b'cookie-sample')
            archive, checksum = backup(src, store)
            self.assertEqual(checksum.read_text().split()[0], _sha256(archive))
            dest.mkdir()
            result = restore(dest, archive, _sha256(archive))
            self.assertEqual((result/'Default'/'Cookies').read_bytes(), b'cookie-sample')
            with self.assertRaises(FileExistsError):
                restore(dest, archive, _sha256(archive))

    def test_wrong_sha_prevents_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base/'src').mkdir()
            archive, _ = backup(base/'src', base/'backups')
            with self.assertRaises(ValueError):
                restore(base/'target', archive, '0' * 64)
            self.assertFalse((base/'target').exists())


if __name__ == '__main__':
    unittest.main()
