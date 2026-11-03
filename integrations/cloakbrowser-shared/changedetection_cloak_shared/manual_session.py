"""Authenticated human-operated page sessions in the *existing* BrowserManager.

Only one manual session may exist per application process. Sessions hold a normal
_ContextLease/_ManagedPage so they count towards CLOAKBROWSER_MAX_PAGES. Playwright
objects never leave BrowserManager's asyncio loop. No CDP debugging port is exposed.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import threading
import time
from dataclasses import dataclass

from loguru import logger
from .manager import manager, _ContextLease
from .page_readiness import page_challenge

_SESSION_SECONDS = 15 * 60
_MAX_FRAME_BYTES = 3 * 1024 * 1024


class ManualSessionError(RuntimeError):
    pass


@dataclass
class _Session:
    token: str
    owner: str
    watch_uuid: str | None
    browser_generation: int
    lease: _ContextLease
    page: object
    last_active: float
    address: str
    closed: bool = False


class ManualSessionManager:
    def __init__(self):
        self._guard = threading.RLock()
        self._session = None
        self._reserved = set()
        self._opening = False
        self._expiry_tasks = set()

    def is_reserved(self, watch_uuid):
        if not watch_uuid:
            return False
        with self._guard:
            return str(watch_uuid) in self._reserved

    def _get(self, token, owner):
        session = self._session
        if session is None or session.closed or session.token != token or session.owner != owner:
            raise ManualSessionError('Manual session has ended or belongs to another login')
        if not manager.session_alive(session.browser_generation):
            raise ManualSessionError('Shared browser restarted; reopen the manual session')
        if time.monotonic() - session.last_active > _SESSION_SECONDS:
            raise ManualSessionError('Manual session expired after 15 minutes of inactivity')
        return session

    def inspect(self, owner):
        """Never reveal another operator's URL or control token."""
        with self._guard:
            entry = self._session
            if entry is None or entry.closed:
                return {'active': False, 'opening': self._opening}
            age = time.monotonic() - entry.last_active
            if not manager.session_alive(entry.browser_generation) or age > _SESSION_SECONDS:
                return {'active': False, 'opening': True}
            yours = entry.owner == owner
            result = {'active': True, 'owned': yours,
                      'seconds_remaining': max(0, int(_SESSION_SECONDS - age))}
            if yours:
                result.update({'url': entry.address, 'session': entry.token,
                               'generation': entry.browser_generation,
                               'watch_uuid': entry.watch_uuid or ''})
            return result

    async def _resume_owned(self, token, owner):
        """Transfer control: a previous tab's token stops working."""
        with self._guard:
            entry = self._get(token, owner)
            entry.token = secrets.token_urlsafe(32)
        # Retain the existing expiry supervisor; token rotation transfers control,
        # it must not create a new lifetime supervisor or reset idle timeout.
        return {'session': entry.token, 'generation': entry.browser_generation}

    def resume(self, token, owner):
        return manager.call_sync(self._resume_owned(token, owner), timeout=15)

    def _reserve(self, watch_uuid):
        with self._guard:
            if self._opening or self._session is not None:
                raise ManualSessionError('Another manual browser session is active. Close it first.')
            self._opening = True
            if watch_uuid:
                self._reserved.add(watch_uuid)

    def _unreserve(self, watch_uuid):
        with self._guard:
            if watch_uuid:
                self._reserved.discard(watch_uuid)
            self._opening = False

    async def _create(self, token, owner, watch_uuid, url):
        await manager._ensure_context()
        # The same semaphore and owned browser generation as automated tabs.
        lease = _ContextLease(manager, {})
        page = await lease.new_page()
        try:
            # Validate *each main-frame navigation*, including redirects and
            # user-initiated clicks. DNS validation is blocking; offload it.
            from changedetectionio.validate_url import is_fetch_url_allowed

            async def guard_navigation(route, request):
                if request.is_navigation_request():
                    allowed, _ = await asyncio.to_thread(is_fetch_url_allowed, request.url)
                    if not allowed:
                        logger.warning('Manual browser blocked disallowed navigation')
                        await route.abort('blockedbyclient')
                        return
                await route.continue_()

            await page.route('**/*', guard_navigation)
            # Popups opened by page scripts are not represented by our Page
            # lease and would evade the tab semaphore. Close them immediately.
            def close_popup(popup):
                task = asyncio.create_task(popup.close())
                task.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
            page.on('popup', close_popup)
            await page.goto(url, wait_until='domcontentloaded', timeout=35000)
        except BaseException:
            await lease.close()
            raise
        session = _Session(token, owner, watch_uuid, manager._generation,
                           lease, page, time.monotonic(), url)
        # An independent timer, not driven by screenshot polling, frees tabs if
        # the browser window is abandoned. Its generation is checked on cleanup.
        task = asyncio.create_task(self._expiry_watch(session), name='manual-session-expiry')
        self._expiry_tasks.add(task)
        task.add_done_callback(self._expiry_tasks.discard)
        return session

    async def _expiry_watch(self, session):
        # Bound to the immutable session object, not the rotatable bearer token.
        while True:
            await asyncio.sleep(10)
            with self._guard:
                if self._session is not session or session.closed:
                    return
                expired = time.monotonic() - session.last_active > _SESSION_SECONDS
                dead = not manager.session_alive(session.browser_generation)
                token = session.token
            if expired or dead:
                logger.info('Manual browser session ended (expired or browser generation changed)')
                try:
                    await self._dispose(token)
                except Exception as exc:
                    logger.warning('Manual session cleanup was interrupted: {}', type(exc).__name__)
                return

    def open(self, owner, url, watch_uuid=None):
        self._reserve(watch_uuid)
        try:
            # Prevent opening while an already-running watch would mutate the
            # same domain's shared cookies/state. Other watches remain active.
            if watch_uuid:
                from changedetectionio import worker_pool
                if worker_pool.is_watch_running(watch_uuid):
                    raise ManualSessionError('This watch is currently checking. Retry once it finishes.')
            token = secrets.token_urlsafe(32)
            session = manager.call_sync(self._create(token, owner, watch_uuid, url), timeout=55)
            with self._guard:
                self._session = session
                self._opening = False
            return {'session': token, 'generation': session.browser_generation}
        except BaseException:
            self._unreserve(watch_uuid)
            raise

    async def _dispose(self, token):
        with self._guard:
            session = self._session
            if not session or session.token != token:
                return None
            session.closed = True
        try:
            await session.lease.close()
        finally:
            with self._guard:
                if self._session is session:
                    self._session = None
                    self._reserved.discard(session.watch_uuid)
        return session.watch_uuid

    async def _close_owned(self, token, owner):
        # The owner must be able to close even after expiry or a generation
        # failure; those checks are for interactive operations, not cleanup.
        session = self._session
        if not session or session.token != token or session.owner != owner:
            raise ManualSessionError('Manual session not found for this login')
        return await self._dispose(token)

    def close(self, token, owner):
        return manager.call_sync(self._close_owned(token, owner), timeout=25)

    async def _frame(self, token, owner):
        session = self._get(token, owner)
        data = await session.page.screenshot(type='jpeg', quality=65,
                                             full_page=False, timeout=12000)
        if len(data) > _MAX_FRAME_BYTES:
            raise ManualSessionError('Browser screenshot exceeds size limit')
        return data

    def frame(self, token, owner):
        return manager.call_sync(self._frame(token, owner), timeout=20)

    async def _status(self, token, owner):
        session = self._get(token, owner)
        page = session.page
        url = page.url
        session.address = url
        # Never return cookies/LocalStorage values to the client.
        # Navigation can temporarily destroy the JavaScript execution context.
        # A transient status read must not close the still-running browser session.
        try:
            info = await page.evaluate('''() => ({
                width: window.innerWidth, height: window.innerHeight,
                localStorageKeys: (() => { try { return localStorage.length; } catch (_) { return null; } })()
            })''')
            if not isinstance(info, dict):
                info = {}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug('Manual browser viewport unavailable during navigation: {}', exc)
            info = {}
        try:
            cookies = await page.context.cookies([url]) if url.startswith(('http://', 'https://')) else []
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug('Manual browser cookies unavailable during navigation: {}', exc)
            cookies = []
        return {
            'url': url,
            'width': max(1, int(info.get('width') or 1366)),
            'height': max(1, int(info.get('height') or 768)),
            'cookie_count': len(cookies),
            'local_storage_keys': info.get('localStorageKeys'),
            'profile_lock_held': manager.profile_lock_held(),
            'generation': session.browser_generation,
            'challenge': await page_challenge(page),
            'seconds_remaining': max(0, int(_SESSION_SECONDS - (time.monotonic() - session.last_active))),
        }

    def status(self, token, owner):
        return manager.call_sync(self._status(token, owner), timeout=20)

    async def _action(self, token, owner, action, args):
        session = self._get(token, owner)
        page = session.page
        x, y = args.get('x'), args.get('y')
        if action in {'click', 'move', 'down', 'up', 'scroll'}:
            if x is None or y is None:
                raise ManualSessionError('Missing pointer coordinates')
            x, y = float(x), float(y)
            if not (0 <= x <= 10000 and 0 <= y <= 10000):
                raise ManualSessionError('Pointer coordinates out of bounds')
            if action == 'click':
                await page.mouse.click(x, y)
            elif action == 'move':
                await page.mouse.move(x, y)
            elif action == 'down':
                await page.mouse.move(x, y)
                await page.mouse.down(button='left')
            elif action == 'up':
                await page.mouse.move(x, y)
                await page.mouse.up(button='left')
            else:
                dx, dy = float(args.get('dx') or 0), float(args.get('dy') or 0)
                if abs(dx) > 3000 or abs(dy) > 3000:
                    raise ManualSessionError('Scroll distance too large')
                await page.mouse.move(x, y)
                await page.mouse.wheel(dx, dy)
        elif action == 'key':
            key = str(args.get('key') or '')
            # Only normal keyboard keys; do not expose arbitrary browser/CDP commands.
            allowed = {'Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'Space',
                       'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End',
                       'PageUp', 'PageDown'}
            if key not in allowed and not (len(key) == 1 and key.isprintable()):
                raise ManualSessionError('Unsupported keyboard key')
            await page.keyboard.press(key)
        elif action == 'text':
            value = args.get('text')
            if not isinstance(value, str) or len(value) > 512:
                raise ManualSessionError('Text must be at most 512 characters')
            await page.keyboard.insert_text(value)
        elif action == 'navigate':
            url = args.get('url')
            if not isinstance(url, str) or len(url) > 2048:
                raise ManualSessionError('Invalid navigation URL')
            if not url.lower().startswith(('http://', 'https://')):
                raise ManualSessionError('Navigation requires an http(s) URL')
            from changedetectionio.validate_url import is_fetch_url_allowed
            allowed, reason = await asyncio.to_thread(is_fetch_url_allowed, url)
            if not allowed:
                raise ManualSessionError(f'Navigation refused: {reason}')
            await page.goto(url, wait_until='domcontentloaded', timeout=35000)
            session.address = page.url
        elif action == 'back':
            await page.go_back(wait_until='domcontentloaded', timeout=30000)
            session.address = page.url
        elif action == 'forward':
            await page.go_forward(wait_until='domcontentloaded', timeout=30000)
            session.address = page.url
        elif action == 'resize':
            # Manual-only Playwright viewport. No browser restart, and no
            # change to other monitoring Pages in the shared Context.
            width, height = args.get('width'), args.get('height')
            if (type(width) is not int or type(height) is not int or
                    not 320 <= width <= 2560 or not 240 <= height <= 1800):
                raise ManualSessionError('Invalid viewport dimensions')
            await page.set_viewport_size({'width': width, 'height': height})
        elif action == 'refresh':
            await page.reload(wait_until='domcontentloaded', timeout=30000)
            session.address = page.url
        else:
            raise ManualSessionError('Unsupported manual action')
        session.last_active = time.monotonic()
        return {'ok': True}

    def action(self, token, owner, action, args):
        return manager.call_sync(self._action(token, owner, action, args), timeout=40)


manual_sessions = ManualSessionManager()
