"""Pure asyncio CDP-screencast regression tests; no browser needed."""
import asyncio
import base64
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/manual_screencast.py'


class FakeCDP:
    def __init__(self):
        self.commands = []
        self.callback = None
        self.detached = False

    def on(self, event, callback):
        assert event == 'Page.screencastFrame'
        self.callback = callback

    async def send(self, command, options=None):
        self.commands.append((command, options))

    async def detach(self):
        self.detached = True


class FakeContext:
    def __init__(self, cdp):
        self.cdp = cdp
        self.target = None

    async def new_cdp_session(self, page):
        self.target = page
        return self.cdp


class ScreencastTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # The standalone test environment doesn't install production loguru.
        fake_loguru = types.ModuleType('loguru')
        fake_loguru.logger = types.SimpleNamespace(debug=lambda *a: None)
        with patch.dict(sys.modules, {'loguru': fake_loguru}):
            spec = importlib.util.spec_from_file_location('test_screencast_module', SRC)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.module = module
        self.cdp = FakeCDP()
        self.page = types.SimpleNamespace(context=FakeContext(self.cdp))
        self.managed = types.SimpleNamespace(_page=self.page)
        self.cast = module.ManualScreencast(self.managed)
        await self.cast.start()

    async def asyncTearDown(self):
        await self.cast.stop()

    async def test_targets_unwrapped_page_and_starts_stops(self):
        self.assertIs(self.page.context.target, self.page)
        self.assertEqual(self.cdp.commands[0][0], 'Page.startScreencast')
        await self.cast.stop()
        self.assertTrue(self.cdp.detached)
        self.assertIn('Page.stopScreencast', [c[0] for c in self.cdp.commands])

    async def test_latest_frame_replaces_older_and_acks_every_id(self):
        def emit(sid, payload):
            self.cdp.callback({'sessionId': sid, 'data':base64.b64encode(payload).decode('ascii')})
        emit(1, b'old')
        emit(2, b'new')
        await asyncio.sleep(0)
        frame, info = await self.cast.next_frame()
        self.assertEqual(frame, b'new')
        self.assertEqual(info['cdp_dropped'], 1)
        self.assertEqual(info['engine'], 'cdp')
        self.assertEqual([c[1]['sessionId'] for c in self.cdp.commands if c[0] == 'Page.screencastFrameAck'], [1,2])

    async def test_static_page_has_no_frame_and_oversized_data_dropped(self):
        self.cdp.callback({'sessionId': 3, 'data':base64.b64encode(b'a' * (self.module.MAX_JPEG_BYTES + 1)).decode('ascii')})
        self.assertEqual(self.cast.queue.qsize(), 0)
        self.assertIsNone(await self.cast.next_frame(timeout=0.01))

    async def test_malformed_payload_is_ignored_but_acknowledged(self):
        self.cdp.callback({'sessionId': 4, 'data': '!not-base64!'})
        await asyncio.sleep(0)
        self.assertEqual(self.cast.queue.qsize(), 0)
        self.assertIn(('Page.screencastFrameAck', {'sessionId':4}), self.cdp.commands)


if __name__ == '__main__':
    unittest.main()
