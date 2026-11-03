#!/usr/bin/env python3
"""Validate changedetection plugin registration; --browser also tests Chromium."""
import argparse
import asyncio
import importlib.metadata as metadata
import os
import sys

def check_plugin():
    entries = [e for e in metadata.entry_points(group="changedetectionio")
               if e.name == "cloak_browser"]
    assert len(entries) == 1, f"Expected one CloakBrowser entry point; got {len(entries)}"
    from changedetectionio.content_fetchers import get_plugin_fetchers
    fetchers = get_plugin_fetchers()
    assert "html_cloakbrowser" in fetchers, f"Registered fetchers: {list(fetchers)}"
    fetcher = fetchers["html_cloakbrowser"]
    assert fetcher.supports_browser_steps
    assert fetcher.supports_screenshots
    for name in ("changedetection.io-cloak-browser", "cloakbrowser", "playwright"):
        print(f"[OK] {name} {metadata.version(name)}", flush=True)
    print("[OK] html_cloakbrowser registered", flush=True)

async def check_browser(url):
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True, humanize=False)
    try:
        page = await browser.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            assert response is not None and response.ok, "Navigation unsuccessful"
            assert await page.evaluate("() => 2 + 2") == 4, "JavaScript failed"
            screenshot = await page.screenshot()
            assert screenshot.startswith(bytes((137, 80, 78, 71))), "PNG screenshot failed"
            print(f"[OK] Chromium navigation, JavaScript, screenshot ({len(screenshot)} bytes)", flush=True)
        finally:
            await page.close()
    finally:
        await browser.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--url", default="https://example.com")
    args = parser.parse_args()
    check_plugin()
    if args.browser:
        if not os.environ.get("CLOAKBROWSER_LICENSE_KEY"):
            raise RuntimeError("Missing CLOAKBROWSER_LICENSE_KEY")
        asyncio.run(check_browser(args.url))
    else:
        print("[SKIP] Real browser launch; add --browser to test Chromium")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
