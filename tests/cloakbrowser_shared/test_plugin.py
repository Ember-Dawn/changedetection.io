"""Test glue against a tiny synthetic implementation of upstream package APIs.

This is not a substitute for a real upstream-plugin/Chromium integration test.
"""
import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
try:
    import loguru
except ImportError:
    sys.modules['loguru'] = types.SimpleNamespace(logger=types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None))

from changedetection_cloak_shared.manager import BrowserManager, _SHARED_FETCH, manager


class StandInPage:
    def is_closed(self):
        return getattr(self, '_closed', False)

    async def close(self):
        self._closed = True

    async def set_extra_http_headers(self, h):
        self.headers = h


class StandInContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def new_page(self):
        p = StandInPage()
        self.pages.append(p)
        return p

    async def close(self):
        self.closed = True


class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_fetcher_routes_launch_and_original_remains_available(self):
        from changedetection_cloak_shared.manager import install_launch_router
        launch_calls = []
        async def original_launch(**kwargs):
            launch_calls.append(kwargs)
            return object()
        fake_cloak = types.ModuleType('cloakbrowser')
        fake_cloak.launch_async = original_launch
        fake_hook = types.ModuleType('changedetectionio.pluggy_interface')
        fake_hook.hookimpl = lambda fn: fn
        upstream_pkg = types.ModuleType('changedetection_cloak_browser')
        upstream_pkg.__path__ = []
        upstream_mod = types.ModuleType('changedetection_cloak_browser.fetcher')

        class Orig:
            async def run(self, **kwargs):
                import cloakbrowser
                lease = await cloakbrowser.launch_async(headless=True)
                ctx = await lease.new_context(extra_http_headers={'x-test': 'yes'})
                try:
                    page = await ctx.new_page()
                    self.content = page.headers['x-test']
                finally:
                    await ctx.close()
                    await lease.close()

        upstream_mod.register_content_fetcher = lambda: ('html_cloakbrowser', Orig)
        # Manager singleton is the one used by plugin.py.
        real_context = StandInContext()
        async def fake_start():
            if manager._context is None:
                manager._context = real_context
        old_start, old_ctx = manager._ensure_context, manager._context
        manager._ensure_context, manager._context = fake_start, None
        with patch.dict(sys.modules, {
            'cloakbrowser': fake_cloak,
            'changedetectionio.pluggy_interface': fake_hook,
            'changedetection_cloak_browser': upstream_pkg,
            'changedetection_cloak_browser.fetcher': upstream_mod,
        }):
            try:
                from changedetection_cloak_shared.plugin import register_content_fetcher
                name, cls = register_content_fetcher()
                self.assertEqual(name, 'html_cloakbrowser_shared')
                obj = cls()
                await obj.run(watch_uuid='test')
                self.assertEqual(obj.content, 'yes')
                self.assertEqual(len(real_context.pages), 1)
                self.assertTrue(real_context.pages[0].is_closed())
                self.assertFalse(real_context.closed)
                self.assertEqual(launch_calls, [])
                await fake_cloak.launch_async(headless=True)  # unmarked call delegates
                self.assertEqual(len(launch_calls), 1)
            finally:
                manager.stop()
                manager._ensure_context, manager._context = old_start, old_ctx
                manager._stopping = False
                manager._thread, manager._loop = None, None


if __name__ == '__main__':
    unittest.main()
