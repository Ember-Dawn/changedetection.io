"""Scoped optional wait for *valid* required product data before upstream HTML capture."""
import asyncio
import contextvars
import time

PRODUCT_READINESS = contextvars.ContextVar('product_readiness', default=None)

async def wait_until_ready(page, readiness):
    if not readiness:
        return
    from changedetectionio.product_extraction import evaluate, RuleError
    seconds = max(0, min(30, int(readiness.get('wait_seconds', 0))))
    deadline = time.monotonic() + seconds
    while True:
        # The challenge check is also performed by the normal managed Page hook.
        # Never keep polling a known verification page.
        from .page_readiness import page_challenge
        kind = await page_challenge(page)
        if kind:
            from changedetectionio.content_fetchers.exceptions import PageUnloadable
            raise PageUnloadable(url=page.url, message=f'{kind} still displayed; monitoring result was not saved')
        try:
            html = await page.content()
            data = await asyncio.to_thread(evaluate, readiness['rule'], html)
            ok_price = not readiness.get('require_price') or data.price is not None
            ok_stock = not readiness.get('require_stock') or any(
                getattr(data, name) is not None for name in ('in_stock', 'pickup', 'shipping'))
            if ok_price and ok_stock:
                return
        except RuleError:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return  # The processor raises the specific extraction error later.
        await asyncio.sleep(min(1, remaining))
