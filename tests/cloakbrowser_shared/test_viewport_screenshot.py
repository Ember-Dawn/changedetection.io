"""Regression for screenshots captured from persistent BrowserContexts (viewport=None)."""
import unittest
from unittest.mock import AsyncMock


class FakePage:
    def __init__(self, original_viewport, height):
        self.viewport_size = original_viewport
        self.height = height
        self.request_gc = AsyncMock()
        self.screenshot = AsyncMock(return_value=b'jpeg')
        self.set_viewport_size = AsyncMock(side_effect=self._set_viewport)

    def _set_viewport(self, value):
        self.viewport_size = dict(value)

    async def evaluate(self, expression, *args):
        if expression == "document.documentElement.scrollHeight":
            return self.height
        if expression == "document.documentElement.scrollWidth":
            return 1366
        if expression == "({width: window.innerWidth, height: window.innerHeight})":
            return {"width": 1366, "height": 768}
        return None


class ScreenshotViewportTests(unittest.IsolatedAsyncioTestCase):
    async def test_none_viewport_without_resize(self):
        from changedetectionio.content_fetchers.playwright import capture_full_page_async
        page = FakePage(None, 700)
        self.assertEqual(await capture_full_page_async(page), b'jpeg')
        page.set_viewport_size.assert_not_awaited()
        page.screenshot.assert_awaited_once()

    async def test_none_viewport_with_resize(self):
        from changedetectionio.content_fetchers.playwright import capture_full_page_async
        page = FakePage(None, 804)
        self.assertEqual(await capture_full_page_async(page), b'jpeg')
        self.assertEqual(page.set_viewport_size.await_count, 2)
        self.assertEqual(page.set_viewport_size.await_args.args[0],
                         {"width": 1366, "height": 768})

    async def test_existing_fixed_viewport(self):
        from changedetectionio.content_fetchers.playwright import capture_full_page_async
        page = FakePage({"width": 1280, "height": 800}, 700)
        self.assertEqual(await capture_full_page_async(page), b'jpeg')
        page.set_viewport_size.assert_not_awaited()
