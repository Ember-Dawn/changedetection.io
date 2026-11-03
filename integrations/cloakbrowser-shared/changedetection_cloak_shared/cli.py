"""Small standalone shared browser smoke test, run inside the Docker image."""
import asyncio
import os
from .manager import manager


async def test():
    async def body():
        lease = await manager._borrow_browser()
        context = await lease.new_context()
        try:
            page = await context.new_page()
            await page.goto('https://example.com', wait_until='domcontentloaded')
            assert await page.evaluate('() => 2 + 2') == 4
            assert (await page.screenshot()).startswith(bytes((137, 80, 78, 71)))
            print('Shared browser: navigation / JS / screenshot PASS', flush=True)
        finally:
            await lease.close()
    return await manager.run_fetch('smoke', body)


if __name__ == '__main__':
    if not os.environ.get('CLOAKBROWSER_LICENSE_KEY'):
        raise SystemExit('CLOAKBROWSER_LICENSE_KEY is required')
    try:
        asyncio.run(test())
    finally:
        manager.stop()
