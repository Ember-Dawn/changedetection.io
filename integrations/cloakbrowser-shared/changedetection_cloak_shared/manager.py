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
import time
import uuid
from collections import defaultdict
from enum import Enum
from .profile_manager import ProfileLock

from loguru import logger

_SHARED_FETCH = contextvars.ContextVar('changedetection_cloak_shared_fetch', default=False)


class BrowserState(str, Enum):
    STOPPED = 'STOPPED'
    STARTING = 'STARTING'
    RUNNING = 'RUNNING'
    RECOVERING = 'RECOVERING'
    STOPPING = 'STOPPING'
    FAILED = 'FAILED'



def _int_env(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f'{name} must be >= 1')
    return value


class _ManagedPage:
    """Idempotent page lease. A slot is free only after close is confirmed.

    A timed-out close remains tracked: an eventual close can safely release the
    slot, but an unconfirmed close invalidates the current browser generation.
    """

    def __init__(self, page, semaphore, manager=None, generation=None):
        self._page = page
        self._semaphore = semaphore
        self._manager = manager
        self._generation = generation
        self._released = False
        self._close_task = None
        if manager is not None:
            with manager._lock:
                manager._live_pages.add(self)

    def __getattr__(self, name):
        return getattr(self._page, name)

    async def wait_for_timeout(self, milliseconds):
        """Upstream-fetcher compatibility seam: wait, then inspect challenge.

        Version 0.1.1 of the upstream fetcher calls this hook after navigation
        and before extracting XPath/HTML. Only shared scheduled fetches inspect.
        Other callers retain ordinary Playwright wait_for_timeout behavior.
        """
        await self._page.wait_for_timeout(milliseconds)
        if _SHARED_FETCH.get():
            await self._check_verification_after_upstream_wait()
            from .product_ready import PRODUCT_READINESS, wait_until_ready
            readiness = PRODUCT_READINESS.get()
            if readiness:
                await wait_until_ready(self._page, readiness)

    async def _check_verification_after_upstream_wait(self):
        from .page_readiness import page_challenge
        kind = await page_challenge(self._page)
        if kind:
            from changedetectionio.content_fetchers.exceptions import PageUnloadable
            raise PageUnloadable(url=self._page.url,
                                 message=f'{kind} still displayed; monitoring result was not saved')

    def _confirmed_closed(self):
        try:
            return bool(self._page.is_closed())
        except Exception:
            return False

    def _release_when_safe(self):
        # The old semaphore stays with this lease even when a new generation
        # starts. Releasing exactly once cannot inflate the new generation cap.
        gone = (self._manager is not None and
                (self._manager._generation != self._generation or
                 (self._manager._context is not None and
                  self._manager._browser_definitely_gone())))
        if not self._released and (self._confirmed_closed() or gone):
            self._released = True
            self._semaphore.release()
            if self._manager is not None:
                with self._manager._lock:
                    self._manager._live_pages.discard(self)
        return self._released

    def _on_close_done(self, task):
        # Keep the closure callback independent from the caller's cancellation.
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if self._manager is not None:
                self._manager.invalidate(f'Page close failed: {exc}')
        if not self._release_when_safe() and self._manager is not None:
            self._manager.invalidate('Page close did not confirm closure')

    async def close(self, *args, **kwargs):
        if self._release_when_safe():
            return
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_underlying(*args, **kwargs))
            self._close_task.add_done_callback(self._on_close_done)
        try:
            await asyncio.wait_for(asyncio.shield(self._close_task), timeout=8)
        except asyncio.CancelledError:
            # Keep the Page close running; shutdown/recovery tracks the task.
            try:
                await asyncio.wait_for(asyncio.shield(self._close_task), timeout=5)
            except (Exception, asyncio.CancelledError):
                pass
            self._release_when_safe()
            raise
        except Exception:
            self._release_when_safe()
            if self._manager is not None:
                self._manager.invalidate('Page did not close cleanly')
            raise
        if not self._release_when_safe():
            if self._manager is not None:
                self._manager.invalidate('Page close returned without closing page')
            raise RuntimeError('Page closure not confirmed')

    async def _close_underlying(self, *args, **kwargs):
        if not self._confirmed_closed():
            await self._page.close(*args, **kwargs)


class _ContextLease:
    """Per-task facade of a persistent context. Closing does not close Profile."""

    def __init__(self, manager, options):
        self.manager = manager
        self.options = options
        self.pages = []
        self.generation = manager._generation

    async def new_page(self):
        # A preview opened under an old browser generation cannot reuse a
        # fresh Context after the old browser has crashed or been restarted.
        if self.manager._stopping or self.manager._generation != self.generation:
            raise RuntimeError('Shared browser session expired; reopen the preview')
        self.manager.validate_options(self.options)
        await self.manager._semaphore.acquire()
        if self.manager._stopping or self.manager._generation != self.generation:
            self.manager._semaphore.release()
            raise RuntimeError('Shared browser session expired while waiting for a tab')
        try:
            page = await self.manager._context.new_page()
            try:
                from changedetectionio.product_extraction.viewport import desktop_viewport
                await page.set_viewport_size(desktop_viewport())
            except BaseException:
                await page.close()
                raise
        except BaseException:
            self.manager._semaphore.release()
            raise
        managed = _ManagedPage(page, self.manager._semaphore, self.manager, self.manager._generation)
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
        errors = []
        for page in list(self.pages):
            try:
                await page.close()
            except Exception as exc:
                errors.append(exc)
        self.pages.clear()
        if errors:
            raise RuntimeError(f'{len(errors)} page(s) could not close: {errors[0]}')


class _BrowserLease:
    """Limited Browser protocol consumed by the upstream fetcher and live UI."""

    def __init__(self, manager):
        self.manager = manager
        self.contexts = []

    async def new_context(self, **kwargs):
        self.manager.validate_options(kwargs)
        if self.manager._stopping:
            raise RuntimeError('Shared CloakBrowser manager is stopping')
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
        self._state = BrowserState.STOPPED
        self._last_error = None
        self._restart_count = 0
        self._generation = 0
        self._started_at = None
        self._unhealthy = False
        self._active_tasks = set()
        self._preview_tasks = set()
        self._live_pages = set()
        self._profile_lock = None
        self._startup_error = None
        self._max_pages = _int_env('CLOAKBROWSER_MAX_PAGES', 3)
        self._live_mode = False

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._launch_lock = asyncio.Lock()
            self._semaphore = asyncio.Semaphore(self._max_pages)
        except BaseException as exc:
            self._startup_error = exc
            self._started.set()
            loop.close()
            self._loop = None
            return
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
                self._startup_error = None
                self._thread = threading.Thread(target=self._run_loop, name='CloakBrowserSharedLoop', daemon=True)
                self._thread.start()
        if not self._started.wait(10):
            raise TimeoutError('Shared CloakBrowser event loop did not start')
        if self._startup_error is not None:
            raise RuntimeError('Shared CloakBrowser loop initialization failed') from self._startup_error
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError('Shared CloakBrowser loop is unavailable')
        return self._loop

    def _browser_definitely_gone(self):
        ctx = self._context
        if ctx is None:
            return True
        try:
            if callable(getattr(ctx, 'is_closed', None)) and ctx.is_closed():
                return True
            browser = getattr(ctx, 'browser', None)
            if browser is not None and not browser.is_connected():
                return True
        except Exception:
            return False
        return False

    def validate_options(self, options):
        headers = options.get('extra_http_headers') or {}
        header_ua = next((v for k, v in headers.items()
                          if str(k).lower() == 'user-agent'), None)
        if header_ua and header_ua != self._user_agent:
            raise ValueError('Per-watch User-Agent header requires isolated CloakBrowser')
        ua = options.get('user_agent')
        if ua and ua != self._user_agent:
            raise ValueError('Per-watch User-Agent requires isolated CloakBrowser')
        if options.get('proxy'):
            _proxy_compatibility_error(options['proxy'])

    def _context_alive(self):
        ctx = self._context
        if ctx is None or self._unhealthy:
            return False
        try:
            if callable(getattr(ctx, 'is_closed', None)) and ctx.is_closed():
                return False
            browser = getattr(ctx, 'browser', None)
            if browser is not None and not browser.is_connected():
                return False
        except Exception:
            return False
        return True

    def invalidate(self, reason):
        self._unhealthy = True
        self._last_error = str(reason)
        logger.warning('Shared CloakBrowser invalidated: {}', reason)

    async def _discard_context(self):
        ctx = self._context
        if ctx is None:
            return
        current = asyncio.current_task()
        others = [task for task in (self._active_tasks | self._preview_tasks)
                  if task is not current and not task.done()]
        for task in others:
            task.cancel()
        if others:
            try:
                await asyncio.wait_for(asyncio.gather(*others, return_exceptions=True), 8)
            except asyncio.TimeoutError:
                self._state = BrowserState.FAILED
                raise RuntimeError('Old browser jobs did not stop; refusing to reopen same Profile')
        # A close task that outlived its caller must be settled before a new
        # Context may open the same Profile.
        closing = [p._close_task for p in self._live_pages
                   if p._generation == self._generation and p._close_task is not None
                   and not p._close_task.done()]
        if closing:
            try:
                await asyncio.wait_for(asyncio.gather(*closing, return_exceptions=True), 8)
            except asyncio.TimeoutError as exc:
                self._state = BrowserState.FAILED
                raise RuntimeError('Page close still pending; refusing Profile reuse') from exc
        gone = self._browser_definitely_gone()
        try:
            await asyncio.wait_for(ctx.close(), 12)
        except Exception as exc:
            if not gone:
                self._state = BrowserState.FAILED
                self._last_error = str(exc)
                raise RuntimeError('Old browser context could not close; refusing concurrent Profile access') from exc
            logger.warning('Context was already disconnected during cleanup: {}', exc)
        self._context = None
        for page in list(self._live_pages):
            page._release_when_safe()
        self._semaphore = asyncio.Semaphore(self._max_pages)

    async def _ensure_context(self):
        if self._stopping:
            raise RuntimeError('Shared CloakBrowser is stopping')
        if self._state is BrowserState.FAILED:
            raise RuntimeError(f'Shared CloakBrowser is FAILED: {self._last_error}')
        if self._context_alive():
            return
        async with self._launch_lock:
            if self._context_alive():
                return
            if self._context is not None:
                self._state = BrowserState.RECOVERING
                await self._discard_context()
                self._restart_count += 1
            else:
                self._state = BrowserState.STARTING
            from cloakbrowser import launch_persistent_context_async
            profile = os.path.realpath(os.getenv('CLOAKBROWSER_PROFILE_DIR', '/browser-profile'))
            os.makedirs(profile, exist_ok=True)
            if self._profile_lock is None:
                lock = ProfileLock(profile)
                lock.acquire()
                self._profile_lock = lock
            humanize = os.getenv('CLOAKBROWSER_HUMANIZE', 'true').lower() not in ('0', 'false', 'no')
            options = {
                'headless': not self._live_mode,
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
            retries = _int_env('CLOAKBROWSER_RECOVERY_MAX_RETRIES', 3)
            delay = _int_env('CLOAKBROWSER_RECOVERY_INITIAL_DELAY', 2)
            for attempt in range(retries):
                try:
                    # Timeout aborts the launch task. A partially started browser
                    # is not necessarily gone; do not retry on ambiguous timeout.
                    ctx = await asyncio.wait_for(launch_persistent_context_async(profile, **options), 60)
                    generation = self._generation + 1
                    def on_close(*_):
                        if self._generation == generation and not self._stopping:
                            self.invalidate('Browser context closed/disconnected')
                    try:
                        ctx.on('close', on_close)
                    except Exception:
                        # Launch succeeded but registration failed; do not
                        # start another browser without closing this instance.
                        try:
                            await asyncio.wait_for(ctx.close(), 12)
                        except Exception as close_error:
                            self._state = BrowserState.FAILED
                            raise RuntimeError('New browser cannot be safely closed') from close_error
                        raise
                    self._context = ctx
                    self._generation = generation
                    self._unhealthy = False
                    self._state = BrowserState.RUNNING
                    self._started_at = time.monotonic()
                    if self._live_mode:
                        from .headed_geometry import fit_headed_window
                        await fit_headed_window()
                    logger.info('Shared CloakBrowser generation {} running; Profile {}', generation, profile)
                    return
                except asyncio.TimeoutError as exc:
                    self._state = BrowserState.FAILED
                    self._last_error = 'Browser launch timed out; verify no orphan Chromium before restart'
                    raise RuntimeError(self._last_error) from exc
                except Exception as exc:
                    self._last_error = f'{type(exc).__name__}: {exc}'
                    if self._state is BrowserState.FAILED or attempt + 1 == retries or self._stopping:
                        self._state = BrowserState.FAILED
                        raise
                    await asyncio.sleep(min(delay * 2 ** attempt, 60))

    async def _borrow_browser(self):
        if self._live_mode:
            raise RuntimeError('Shared browser is in live desktop maintenance mode')
        await self._ensure_context()
        return _BrowserLease(self)

    async def _execute(self, func, *args, **kwargs):
        task = asyncio.current_task()
        with self._lock:
            self._active_tasks.add(task)
        token = _SHARED_FETCH.set(True)
        try:
            if self._live_mode:
                raise RuntimeError('Shared browser is in live desktop maintenance mode')
            await self._ensure_context()
            return await func(*args, **kwargs)
        finally:
            _SHARED_FETCH.reset(token)
            with self._lock:
                self._active_tasks.discard(task)

    async def _run_registered(self, func, args, kwargs):
        return await self._execute(func, *args, **kwargs)

    def session_alive(self, generation):
        """Stable lifetime check for controllers; no Playwright objects leak."""
        return (not self._stopping and not self._unhealthy
                and self._generation == generation
                and self._state is BrowserState.RUNNING)

    def profile_lock_held(self):
        return self._profile_lock is not None

    def status(self):
        with self._lock:
            return {
                'state': self._state.value,
                'mode': 'headed' if self._live_mode else 'headless',
                'generation_id': self._generation,
                'active_jobs': max(sum(len(v) for v in self._pending.values()), len(self._active_tasks)),
                'reserved_slots': max(0, self._max_pages - self._semaphore._value) if self._semaphore else 0,
                'active_pages': sum(1 for p in self._live_pages if not p._confirmed_closed()),
                'closing_pages': sum(1 for p in self._live_pages if p._close_task is not None and not p._close_task.done()),
                'preview_operations': len(self._preview_tasks),
                'profile_lock_held': self._profile_lock is not None,
                'context_alive': self._context_alive(),
                'restart_count': self._restart_count,
                'last_error': self._last_error,
                'uptime_seconds': round(time.monotonic() - self._started_at, 1) if self._started_at else 0,
            }

    def cancel_all(self):
        with self._lock:
            pending = [f for runs in self._pending.values() for f in runs.values()]
        for future in pending:
            future.cancel()
        return len(pending)

    def submit(self, coro):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    async def run_fetch(self, job_watch_uuid, func, *args, **kwargs):
        """Register before adding a done callback (safe for instant completion)."""
        watch = str(job_watch_uuid or '')
        run_id = uuid.uuid4().hex
        future = self.submit(self._run_registered(func, args, kwargs))
        with self._lock:
            self._pending[watch][run_id] = future

        def unregister(_):
            with self._lock:
                runs = self._pending.get(watch)
                if runs is not None:
                    runs.pop(run_id, None)
                    if not runs:
                        self._pending.pop(watch, None)

        # If the task completed before registration, add_done_callback runs
        # immediately, AFTER its slot has been inserted.
        future.add_done_callback(unregister)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            raise

    def cancel_watch(self, watch_uuid):
        """Cancel this watch's active executions even after a Worker loop is stopped."""
        with self._lock:
            futures = list(self._pending.get(str(watch_uuid), {}).values())
        for future in futures:
            future.cancel()
        return len(futures)

    def call_sync(self, coroutine, timeout=None, maintenance=False):
        """Preview operations belong to the manager loop and shutdown registry."""
        if not maintenance:
            from changedetectionio import live_browser_gate
            if live_browser_gate.is_paused():
                coroutine.close()
                raise RuntimeError('Live Browser maintenance: previews temporarily unavailable')
        if timeout is None:
            timeout = _int_env('CLOAKBROWSER_PREVIEW_TIMEOUT', 180)
        if threading.current_thread() is self._thread:
            coroutine.close()
            raise RuntimeError('Cannot call_sync from BrowserManager loop')

        async def tracked_preview():
            task = asyncio.current_task()
            with self._lock:
                self._preview_tasks.add(task)
            try:
                if self._stopping:
                    raise RuntimeError('Shared browser is stopping')
                return await coroutine
            finally:
                with self._lock:
                    self._preview_tasks.discard(task)

        try:
            loop = self._ensure_loop()
            future = asyncio.run_coroutine_threadsafe(tracked_preview(), loop)
        except BaseException:
            coroutine.close()
            raise
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise

    async def _switch_live_mode(self, headed):
        """Run entirely on the owning Playwright loop; keep ProfileLock held.

        All worker and manual/preview traffic must have drained before calling.
        An uncertain close fails closed instead of starting another writer.
        """
        async with self._launch_lock:
            others = [t for t in (self._active_tasks | self._preview_tasks)
                      if t is not asyncio.current_task() and not t.done()]
            if others:
                raise RuntimeError('Browser still has active operations')
            if self._context is not None:
                await self._discard_context()
            self._state = BrowserState.STOPPED
            self._live_mode = bool(headed)
        await self._ensure_context()

    def switch_live_mode(self, headed):
        return self.call_sync(self._switch_live_mode(headed), timeout=115, maintenance=True)

    def stop(self):
        """Stop admission, drain jobs, then flush the persistent Profile."""
        with self._lock:
            was_failed = self._state is BrowserState.FAILED
            self._stopping = True
            self._state = BrowserState.STOPPING
            loop = self._loop
            thread = self._thread
        self.cancel_all()
        if not loop or not thread or not thread.is_alive():
            # A dead manager loop does not prove an unclean Chromium launch
            # has exited. Do not release a lock after an ambiguous failure.
            if was_failed and self._profile_lock:
                self._state = BrowserState.FAILED
                return
            if self._profile_lock:
                self._profile_lock.release()
                self._profile_lock = None
            self._state = BrowserState.STOPPED
            return

        async def shutdown():
            tasks = [t for t in (self._active_tasks | self._preview_tasks) if not t.done()]
            for t in tasks:
                t.cancel()
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
                except asyncio.TimeoutError:
                    logger.warning('Browser jobs did not finish during shutdown')
            closing = [p._close_task for p in self._live_pages if p._close_task and not p._close_task.done()]
            if closing:
                await asyncio.wait_for(asyncio.gather(*closing, return_exceptions=True), 8)
            if self._context is not None:
                await asyncio.wait_for(self._context.close(), 15)
                self._context = None
            for page in list(self._live_pages):
                page._release_when_safe()

        clean = False
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=28)
            clean = True
        except Exception as error:
            self._last_error = str(error)
            logger.warning('Shared CloakBrowser shutdown was incomplete: {}', error)
        finally:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
            thread.join(timeout=5)
            # Release lock only after confirmed Profile close and loop stop.
            if clean and not thread.is_alive():
                if self._profile_lock:
                    self._profile_lock.release()
                    self._profile_lock = None
                self._state = BrowserState.STOPPED
            else:
                self._state = BrowserState.FAILED



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
