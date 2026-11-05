"""Optional CDP Page.screencastFrame producer for an existing manual Page.

All methods are invoked on BrowserManager's asyncio loop. No browser endpoint
is exposed and no Playwright object is shared with Socket.IO threads.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import time

from loguru import logger

MAX_JPEG_BYTES = 3 * 1024 * 1024


class ManualScreencast:
    def __init__(self, managed_page):
        self.page = managed_page
        self.cdp = None
        self.queue = asyncio.Queue(maxsize=1)
        self.running = False
        self.last_frame_at = 0.0
        self.received = 0
        self.dropped = 0
        self._acks = set()

    async def start(self):
        # _ManagedPage is a lease wrapper. CDP must target the actual Page.
        page = getattr(self.page, '_page', self.page)
        self.cdp = await page.context.new_cdp_session(page)
        try:
            self.cdp.on('Page.screencastFrame', self._on_frame)
            self.running = True
            # Experimental CDP options differ by Chromium version; stick to
            # the stable, broadly supported Page.startScreencast arguments.
            await self.cdp.send('Page.startScreencast', {
                'format': 'jpeg', 'quality': 65, 'everyNthFrame': 1,
            })
        except BaseException:
            await self.stop()
            raise

    def _on_frame(self, payload):
        if not self.running or not isinstance(payload, dict):
            return
        sid = payload.get('sessionId')
        # ACK the browser after bounded local handoff; never let an unresponsive
        # browser tab tie CDP flow-control to a remote Socket.IO viewer.
        if type(sid) is int:
            task = asyncio.create_task(self._ack(sid))
            self._acks.add(task)
            task.add_done_callback(self._acks.discard)
        data = payload.get('data')
        if not isinstance(data, str):
            return
        try:
            jpeg = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            return
        if not jpeg or len(jpeg) > MAX_JPEG_BYTES:
            return
        self.received += 1
        self.last_frame_at = time.monotonic()
        if self.queue.full():
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait((jpeg, self.received, self.dropped))

    async def _ack(self, session_id):
        try:
            if self.running and self.cdp is not None:
                await self.cdp.send('Page.screencastFrameAck', {'sessionId': session_id})
        except Exception as exc:
            logger.debug('CDP screencast frame acknowledgement failed: {}', type(exc).__name__)

    async def next_frame(self, timeout=1.0):
        if not self.running:
            raise RuntimeError('CDP screencast is not running')
        try:
            jpeg, received, dropped = await asyncio.wait_for(self.queue.get(), timeout)
            return jpeg, {'capture_ms': None, 'screenshot_ms': None,
                          'dispatch_ms': None, 'bytes': len(jpeg),
                          'cdp_received': received, 'cdp_dropped': dropped,
                          'engine': 'cdp'}
        except asyncio.TimeoutError:
            return None

    async def stop(self):
        self.running = False
        cdp, self.cdp = self.cdp, None
        if cdp is not None:
            try:
                await asyncio.wait_for(cdp.send('Page.stopScreencast'), timeout=3)
            except Exception:
                pass
            try:
                await asyncio.wait_for(cdp.detach(), timeout=3)
            except Exception:
                pass
        pending = list(self._acks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        while not self.queue.empty():
            self.queue.get_nowait()
