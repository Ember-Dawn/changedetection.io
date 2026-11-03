# Shared CloakBrowser add-watch preview: viewport fix

## Verified cause

The user's real log shows:

```text
Shared CloakBrowser generation 1 running; Profile /browser-profile
Time to goto URL 0.35s
Playwright viewport size None page height 804 page width 1366
Error getting current state: 'NoneType' object is not subscriptable
POST /add-watch-ui/snapshot HTTP/1.1 502
```

Browser startup, navigation and the shared Manager all succeeded. The
`capture_full_page_async` screenshot function assumed `page.viewport_size`
was a dictionary. A persistent Chromium BrowserContext can legitimately
report `viewport_size=None`, so screenshot capture failed and the WebUI
returned 502 because the screenshot was empty.

## Fix

`changedetectionio/content_fetchers/playwright.py` now uses
`window.innerWidth` and `window.innerHeight` when `page.viewport_size`
is `None`. It restores viewport dimensions only if capture resized
them. The fix preserves default viewport behavior on other backends.

No changes to CloakBrowser's browser launch, Profile, licensing, cookies,
concurrency or Docker configuration were required.

## Local verification

The supplied ZIP is incremental: copy `payload/` contents into the
repository root, preserving paths. Code is copied into the Docker image,
so **rebuild** after applying:

```bash
docker compose build
docker compose up -d --force-recreate
docker compose logs -f --tail=100 changedetection
```

Test `https://example.com` in the add-watch visual preview with
`html_cloakbrowser_shared`. Expect a screenshot instead of HTTP 502.

Run regression tests locally in your usual project environment with:

```bash
python -m unittest discover -s tests/cloakbrowser_shared -v
```

These tests and the live browser integration have **not** been executed
in the assistant's environment.
