"""No Chromium/network needed; tests core page lease and thread ownership."""
import asyncio
import sys
import unittest
from pathlib import Path
# Dev machine may not have the full changedetection runtime installed.
try:
    import loguru
except ImportError:
    import types
    sys.modules['loguru'] = types.SimpleNamespace(logger=types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manager import BrowserManager, _BrowserLease


class FakePage:
    def __init__(self):
        self.closed = False
        self.headers = None

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True

    async def set_extra_http_headers(self, h):
        self.headers = h


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_leases_share_context_and_release_permits(self):
        manager = BrowserManager()
        manager._context = FakeContext()
        manager._semaphore = asyncio.Semaphore(2)
        lease1 = _BrowserLease(manager)
        lease2 = _BrowserLease(manager)
        ctx1 = await lease1.new_context(extra_http_headers={'Accept-Language': 'zh-CN'})
        ctx2 = await lease2.new_context()
        p1 = await ctx1.new_page()
        p2 = await ctx2.new_page()
        self.assertEqual(p1.headers['Accept-Language'], 'zh-CN')
        self.assertIs(p1._page, manager._context.pages[0])
        self.assertIs(p2._page, manager._context.pages[1])
        self.assertEqual(manager._semaphore._value, 0)
        await p1.close()
        await p1.close()  # idempotent; no double release
        self.assertEqual(manager._semaphore._value, 1)
        await lease1.close()
        self.assertFalse(manager._context.closed)
        await lease2.close()
        self.assertEqual(manager._semaphore._value, 2)
        self.assertFalse(manager._context.closed)

    async def test_user_agent_mismatch_cleans_page(self):
        manager = BrowserManager()
        manager._context = FakeContext()
        manager._semaphore = asyncio.Semaphore(1)
        lease = _BrowserLease(manager)
        ctx = await lease.new_context(user_agent='unexpected-agent')
        with self.assertRaises(ValueError):
            await ctx.new_page()
        self.assertEqual(manager._semaphore._value, 1)
        self.assertTrue(manager._context.pages[0].closed)


if __name__ == '__main__':
    unittest.main()

class ThreadLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_workers_share_one_context_with_page_cap(self):
        manager = BrowserManager()
        # Replace real Chromium startup with a fake context on the manager loop.
        starts = []
        async def fake_start():
            if manager._context is None:
                starts.append('start')
                manager._context = FakeContext()
        manager._ensure_context = fake_start
        active = 0
        peak = 0
        async def fetch():
            nonlocal active, peak
            browser = await manager._borrow_browser()
            ctx = await browser.new_context()
            try:
                page = await ctx.new_page()
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.02)
                    return 'ok'
                finally:
                    active -= 1
                    await page.close()
            finally:
                await browser.close()
        try:
            results = await asyncio.gather(*(manager.run_fetch(str(i), fetch) for i in range(10)))
            self.assertEqual(results, ['ok'] * 10)
            self.assertEqual(starts, ['start'])
            self.assertLessEqual(peak, 3)
            self.assertEqual(active, 0)
        finally:
            manager.stop()

    async def test_cancel_watch_does_not_stop_other_page(self):
        manager = BrowserManager()
        async def fake_start():
            if manager._context is None:
                manager._context = FakeContext()
        manager._ensure_context = fake_start
        async def long_running():
            browser = await manager._borrow_browser()
            ctx = await browser.new_context()
            try:
                await ctx.new_page()
                await asyncio.sleep(30)
            finally:
                await browser.close()
        async def short_running():
            browser = await manager._borrow_browser()
            ctx = await browser.new_context()
            try:
                await ctx.new_page()
                await asyncio.sleep(0.03)
                return 'survived'
            finally:
                await browser.close()
        try:
            bad = asyncio.create_task(manager.run_fetch('bad', long_running))
            good = asyncio.create_task(manager.run_fetch('good', short_running))
            await asyncio.sleep(0.01)
            self.assertEqual(manager.cancel_watch('bad'), 1)
            with self.assertRaises(asyncio.CancelledError):
                await bad
            self.assertEqual(await good, 'survived')
            self.assertEqual(manager._pending, {})
        finally:
            manager.stop()
