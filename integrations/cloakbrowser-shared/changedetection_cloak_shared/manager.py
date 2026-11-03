"""One event loop and one persistent BrowserContext for all shared watches.

All Playwright objects live exclusively on the BrowserManager loop. Watch
workers get only completed fetcher field values, never raw Playwright objects.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import os
import threading
import uuid
from collections import defaultdict

from loguru import logger

_SHARED_FETCH = contextvars.ContextVar('changedetection_cloak_shared_fetch', default=False)


def _int_env(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f'{name} must be >= 1')
    return value


class _ManagedPage:
    """A page wrapper that returns exactly one semaphore permit when closed."""

    def __init__(self, page, semaphore):
        self._page = page
        self._semaphore = semaphore
        self._released = False

    def __getattr__(self, name):
        return getattr(self._page, name)

    async def close(self, *args, **kwargs):
        try:
            if not self._page.is_closed():
                await self._page.close(*args, **kwargs)
        finally:
            if not self._released:
                self._released = True
                self._semaphore.release()


class _ContextLease:
    """Per-task facade of a persistent context. Closing does not close Profile."""

    def __init__(self, manager, options):
        self.manager = manager
        self.options = options
        self.pages = []

    async def new_page(self):
        await self.manager._semaphore.acquire()
        try:
            page = await self.manager._context.new_page()
        except BaseException:
            self.manager._semaphore.release()
            raise
        managed = _ManagedPage(page, self.manager._semaphore)
        self.pages.append(managed)
        try:
            headers = self.options.get('extra_http_headers') or {}
            header_ua = next((value for key, value in headers.items()
                              if str(key).lower() == 'user-agent'), None)
            if header_ua and header_ua != self.manager._user_agent:
                raise ValueError('Shared CloakBrowser forbids per-watch User-Agent header; use isolated mode')
            if headers:
                await managed.set_extra_http_headers(headers)
            ua = self.options.get('user_agent')
            if ua and ua != self.manager._user_agent:
                raise ValueError('Shared CloakBrowser does not support per-watch User-Agent; select isolated CloakBrowser')
            if self.options.get('proxy'):
                _proxy_compatibility_error(self.options['proxy'])
        except BaseException:
            await managed.close()
            raise
        return managed

    async def close(self):
        for page in list(self.pages):
            await page.close()
        self.pages.clear()


class _BrowserLease:
    """Limited Browser protocol consumed by the upstream fetcher and live UI."""

    def __init__(self, manager):
        self.manager = manager
        self.contexts = []

    async def new_context(self, **kwargs):
        if self.manager._context is None:
            raise RuntimeError('Shared CloakBrowser context has been closed')
        context = _ContextLease(self.manager, kwargs)
        self.contexts.append(context)
        return context

    async def close(self):
        # Upstream fetcher's finally must not close the persistent browser.
        for context in list(self.contexts):
            await context.close()
        self.contexts.clear()


class BrowserManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._started = threading.Event()
        self._loop = None
        self._thread = None
        self._context = None
        self._launch_lock = None
        self._semaphore = None
        self._pending = defaultdict(dict)
        self._user_agent = os.getenv('CLOAKBROWSER_SHARED_USER_AGENT') or None
        self._stopping = False

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._launch_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(_int_env('CLOAKBROWSER_MAX_PAGES', 3))
        self._started.set()
        try:
            loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
            self._loop = None

    def _ensure_loop(self):
        with self._lock:
            if self._stopping:
                raise RuntimeError('Shared CloakBrowser manager is stopping')
            if self._thread is None or not self._thread.is_alive():
                self._started.clear()
                self._thread = threading.Thread(target=self._run_loop, name='CloakBrowserSharedLoop', daemon=True)
                self._thread.start()
        if not self._started.wait(10):
            raise TimeoutError('Shared CloakBrowser event loop did not start')
        return self._loop

    async def _ensure_context(self):
        if self._context is not None:
            return
        async with self._launch_lock:
            if self._context is not None:
                return
            from cloakbrowser import launch_persistent_context_async
            profile = os.getenv('CLOAKBROWSER_PROFILE_DIR', '/browser-profile')
            os.makedirs(profile, exist_ok=True)
            humanize = os.getenv('CLOAKBROWSER_HUMANIZE', 'true').lower() not in ('0', 'false', 'no')
            options = {
                'headless': True,
                'accept_downloads': False,
                'humanize': humanize,
                'bypass_csp': True,
                'ignore_https_errors': True,
                'service_workers': os.getenv('PLAYWRIGHT_SERVICE_WORKERS', 'allow'),
            }
            if self._user_agent:
                options['user_agent'] = self._user_agent
            if os.getenv('CLOAKBROWSER_SHARED_PROXY'):
                options['proxy'] = os.getenv('CLOAKBROWSER_SHARED_PROXY')
            self._context = await launch_persistent_context_async(profile, **options)
            logger.info('Shared CloakBrowser started with persistent profile {}', profile)

    async def _borrow_browser(self):
        await self._ensure_context()
        return _BrowserLease(self)

    async def _execute(self, func, *args, **kwargs):
        await self._ensure_context()
        token = _SHARED_FETCH.set(True)
        try:
            return await func(*args, **kwargs)
        finally:
            _SHARED_FETCH.reset(token)

    def submit(self, coro):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    async def run_fetch(self, job_watch_uuid, func, *args, **kwargs):
        """Called on a worker's loop; returns only when original run completes."""
        watch = str(job_watch_uuid or '')
        run_id = uuid.uuid4().hex
        future = self.submit(self._execute(func, *args, **kwargs))
        def forget(_):
            # WorkerThread.stop() may kill the caller event loop before its
            # finally runs. A concurrent.futures callback still clears the job.
            with self._lock:
                runs = self._pending.get(watch)
                if runs is not None:
                    runs.pop(run_id, None)
                    if not runs:
                        self._pending.pop(watch, None)

        with self._lock:
            self._pending[watch][run_id] = future
        future.add_done_callback(forget)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            raise
        finally:
            with self._lock:
                self._pending[watch].pop(run_id, None)
                if not self._pending[watch]:
                    self._pending.pop(watch, None)

    def cancel_watch(self, watch_uuid):
        """Cancel this watch's active executions even after a Worker loop is stopped."""
        with self._lock:
            futures = list(self._pending.get(str(watch_uuid), {}).values())
        for future in futures:
            future.cancel()
        return len(futures)

    def call_sync(self, coroutine, timeout=None):
        """For Flask browser-steps routes; must not be called from manager loop."""
        if timeout is None:
            timeout = _int_env('CLOAKBROWSER_PREVIEW_TIMEOUT', 180)
        loop = self._ensure_loop()
        if threading.current_thread() is self._thread:
            coroutine.close()
            raise RuntimeError('Cannot call_sync from BrowserManager loop')
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise

    def stop(self):
        """Best effort graceful shutdown; one caller owns persistent Context."""
        with self._lock:
            self._stopping = True
            loop = self._loop
            thread = self._thread
            pending = [f for runs in self._pending.values() for f in runs.values()]
        for f in pending:
            f.cancel()
        if not loop or not thread or not thread.is_alive():
            return

        async def close_context():
            if self._context is not None:
                try:
                    await self._context.close()
                finally:
                    self._context = None

        try:
            asyncio.run_coroutine_threadsafe(close_context(), loop).result(timeout=20)
        except (concurrent.futures.TimeoutError, RuntimeError) as error:
            logger.warning('Shared CloakBrowser stop was incomplete: {}', error)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)


manager = BrowserManager()


def install_launch_router():
    """Route only context-marked upstream launches; isolated plugin stays normal.

    Upstream imports ``launch_async`` inside run(). A context variable keeps this
    delegation scoped to the manager loop, even with concurrent isolated checks.
    """
    import cloakbrowser
    if getattr(cloakbrowser.launch_async, '_changedetection_shared_router', False):
        return
    original = cloakbrowser.launch_async

    async def routed(*args, **kwargs):
        if _SHARED_FETCH.get():
            requested_proxy = kwargs.get('proxy')
            expected_proxy = os.getenv('CLOAKBROWSER_SHARED_PROXY') or None
            if requested_proxy and requested_proxy != expected_proxy:
                raise ValueError('Watch proxy differs from shared Profile proxy; use isolated CloakBrowser')
            return await manager._borrow_browser()
        return await original(*args, **kwargs)

    routed._changedetection_shared_router = True
    cloakbrowser.launch_async = routed


def _proxy_compatibility_error(proxy):
    """Refuse a per-watch proxy that does not equal the global profile proxy."""
    from urllib.parse import urlparse
    server = proxy.get('server') or ''
    username, password = proxy.get('username'), proxy.get('password')
    if username and server:
        parsed = urlparse(server)
        requested = f'{parsed.scheme}://{username}:{password}@{parsed.hostname}:{parsed.port}'
    else:
        requested = server or None
    if requested != (os.getenv('CLOAKBROWSER_SHARED_PROXY') or None):
        raise ValueError('Watch proxy differs from shared Profile proxy; use isolated CloakBrowser')
