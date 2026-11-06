"""Pluggy registration of an additional shared CloakBrowser fetch backend.

The original author's html_cloakbrowser remains installed and unchanged as
an isolated fallback. We subclass its *complete* original Fetcher, so all
extraction, Browser Steps, screenshots and exception semantics are inherited.
"""
import os

from changedetectionio.pluggy_interface import hookimpl
from .manager import install_launch_router, manager


@hookimpl
def register_content_fetcher():
    from changedetection_cloak_browser.fetcher import register_content_fetcher as original_factory

    original_name, original_cls = original_factory()
    if original_name != 'html_cloakbrowser':
        raise RuntimeError(f'Unexpected upstream CloakBrowser fetcher: {original_name}')
    install_launch_router()

    class SharedFetcher(original_cls):
        fetcher_description = 'CloakBrowser - Shared persistent profile (experimental)'

        async def run(self, *args, **kwargs):
            # The upstream Fetcher operates on Playwright pages; run the *entire*
            # upstream coroutine on the BrowserManager loop. The manager routes
            # upstream launch_async() to a per-job lease of its shared context.
            # Preserve upstream and per-watch extraction delays unchanged.
            # BrowserManager checks for verification immediately after the
            # upstream navigation settle, before XPath/content extraction.
            from .page_readiness import challenge_kind
            async def with_readiness():
                from .product_ready import PRODUCT_READINESS
                token = PRODUCT_READINESS.set(getattr(self, 'product_readiness', None))
                try:
                    return await super(SharedFetcher, self).run(*args, **kwargs)
                finally:
                    PRODUCT_READINESS.reset(token)
            result = await manager.run_fetch(kwargs.get('watch_uuid'), with_readiness)
            kind = challenge_kind(self.content, url=kwargs.get('url', ''))
            if kind:
                from changedetectionio.content_fetchers.exceptions import PageUnloadable
                raise PageUnloadable(
                    status_code=getattr(self, 'status_code', None),
                    url=kwargs.get('url', ''),
                    message=f'{kind} still displayed; monitoring result was not saved',
                    screenshot=getattr(self, 'screenshot', None) or False,
                )
            return result

        @classmethod
        async def get_browsersteps_browser(cls, proxy=None, keepalive_ms=None):
            # Called from the BrowserManager event loop by our browser-steps
            # integration; return a Browser facade, not the actual Context.
            if proxy:
                from .manager import _proxy_compatibility_error
                _proxy_compatibility_error(proxy)
            return await manager._borrow_browser(), None

    SharedFetcher.__name__ = 'SharedCloakBrowserFetcher'
    return ('html_cloakbrowser_shared', SharedFetcher)
