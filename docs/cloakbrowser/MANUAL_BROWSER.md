# Manual browser: current operation and security

## What it is

The **人工操作** control opens a real CloakBrowser Chromium **Page** in the existing persistent Context. It is **not** a static replica: Chromium loads the page, executes JavaScript and receives real Playwright mouse/keyboard commands. What the operator sees is a periodically fetched **JPEG screenshot** (HTTP polling), not a native streaming remote desktop. The global **Browsers** sidebar entry and Add Watch / existing Watch entry points use the same backend and Profile.

Current implementation paths:

- `changedetectionio/blueprint/manual_browser/__init__.py`: authenticated HTTP endpoints and page template.
- `changedetectionio/blueprint/manual_browser/templates/manual-browser.html`: layout; screenshot area is intended to fill remaining changedetection.io viewport height.
- `changedetectionio/blueprint/manual_browser/static/manual-browser.js`: lightweight UI entrypoint and event wiring.
- `manual-core.js`: authenticated same-origin transport, per-login session token ownership, one ordered action queue, inspect/resume/switch/close lifecycle.
- `manual-stream.js`: JPEG frame polling, status polling, retry/backoff and stale-frame cancellation.
- `manual-input.js`: keyboard, pointer, drag, scroll, address navigation and screenshot-coordinate mapping.
- `manual-layout.js`: full-height viewport and isolated manual Page viewport resize.
- `manual-browser.css`: compact responsive layout, extracted from inline template styles.
- `integrations/cloakbrowser-shared/changedetection_cloak_shared/manual_session.py`: manual Page, session lifetime and input execution on BrowserManager loop.

## Using the UI

1. Log in to changedetection.io with application password protection enabled; the manual API refuses anonymous access even if ordinary monitoring UI pages can be viewed.
2. Open **Browsers** for a free-form URL, or click **人工操作** on a watch. A watch-bound session opens that watch's configured URL.
3. Click **连接浏览器**. Mouse clicks, scrolling, typing, Enter/Backspace and navigation go to the real Page. URL changes are reflected in the editable address bar. The app displays current site Cookie **count**, LocalStorage **count**, current URL and Profile lock status, not secret values.
4. If there is already a manual session belonging to the same login, choose **恢复已有会话** or explicitly close the old session before opening another URL. Recovering rotates the control token, invalidating the old tab's token.
5. For an existing watch, **完成并重新检查** closes the manual Page and conditionally queues one check via the usual worker queue if not paused/running/queued. For a new watch or the global Browsers page, closing manual control is not a substitute for creating a watch; return to Add Watch and refresh the preview.

A browser tab/window closing does not immediately destroy the server-side manual Page; it can be recovered by the same login until its session expires or is closed. **At most one manual session** is kept by the application. The manual Page occupies one of the shared `CLOAKBROWSER_MAX_PAGES` permits, so remaining slots can serve scheduled watches. For a watch-bound session the worker must not concurrently check that watch. Other watches are not automatically paused (they still share cookies, however).

## Session and input constraints

- Human session idle timeout: 15 minutes. One expiry task belongs to each Page session and survives login-token rotation; resuming an old tab does not create another expiry task. Polling screenshots or querying status does **not** count as human activity; interacting refreshes last-active time. Browser generation changes invalidate a session.
- Browser screenshots are JPEG frames over authenticated HTTP requests; transient HTTP 500 during navigation is retried without assuming the remote Page has died. Terminal session/auth errors (401/403/404/409, certain 400 failures) require reconnection.
- The frontend records an in-memory session epoch and matches async callbacks to the current token. Late status/frame/inspection responses from a previous session are ignored, even when a prior browser tab still has in-flight requests. The token is never kept in localStorage or URL parameters.
- Only one screenshot request runs per polling chain. The screenshot URL is revoked when replaced/closed and a hidden tab suspends polling; an abandoned server-side Page still expires under the 15-minute manager supervisor.
- Actions run through one ordered request queue (mouse down/move/up, key, resize and navigation); non-terminal input failures are reported without permanently blocking later commands. Drag capture loss sends a matching mouse-up when the session is still active.
- Actions are limited and validated: click, pointer move/down/up, wheel, selected keys, text (up to 512 chars), navigation, back/forward, refresh and viewport resize. URL and navigation requests go through the app's URL safety checks; popups are closed rather than being allowed to evade Page quotas.
- The UI tracks the displayed screenshot dimensions for accurate click coordinates; the manual Page viewport can be resized independently from other watch Pages.
- Authentication, CSRF, origin checks, per-login ownership tokens and restrictions on remote URL navigation protect the control API; keep server or Cloudflare Access controls as an additional layer. Do not expose Playwright/CDP, VNC or similar raw control ports publicly.

## Profile persistence: what can actually be verified

The host-mounted `browser-profile/` contains Chromium's `Default/Cookies`, `Local State`, `Preferences` and other state. A populated database proves data was written, **not** that a website login or human verification remains valid. The proper check: authenticate on a consenting test website in manual mode, close the manual Page, cleanly stop/restart the container, reopen the same website with shared mode, and verify the website itself still recognizes the session.

The container may write Profile files as UID 0. A host non-root user seeing `Permission denied` is expected for root-owned `Default/` with mode 700. Inspect with `sudo` when needed; do **not** recursively `chmod 777` or chown the active Profile. Back it up offline using [OPERATIONS.md](OPERATIONS.md).

## Limitations and future ideas (not implemented)

- This is screenshot polling plus HTTP input, not 30/60 FPS stream, remote desktop, audio, or OS-window control.
- Popup-based sign-in flows may not work because untracked popups are closed.
- Human verification remains subject to target-site policies and may be requested again; no automatic CAPTCHA-solving guarantee.
- Xvfb + noVNC and CDP screencast/WebSocket are **research options only**. They are not part of the current image or deployed remote-control code. Preserve the current working HTTP method until any alternative is explicitly implemented/tested.

## Frontend verification after round 2 refactor

The browser interface is still **plain JavaScript**, without build tools or framework packages. `manual-browser.html` loads five local `defer` scripts in dependency order and a local CSS file. Update all five together when changing the shared module API; versions are cache-busted in the template. Do not import JavaScript directly from a CDN.

Run the frontend tests (Node 20+ recommended):

```bash
node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs
```

These tests use a simulated DOM and mocked same-origin HTTP API; they cannot substitute for real CloakBrowser tests. On the Docker host, validate initial connection, navigation/refresh, frame recovery after a temporary error, manual Page resizing, mouse drag release, URL synchronization, recovery/switch from a second tab, login ownership and authentication checks, and the watch-bound **完成并重新检查** action.
