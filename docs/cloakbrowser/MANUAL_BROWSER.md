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
- Browser screenshots prefer authenticated Socket.IO binary JPEG frames with one-frame acknowledgement and adaptive 10/5/2 FPS caps; HTTP JPEG polling remains a fallback. transient HTTP 500 during navigation is retried without assuming the remote Page has died. Terminal session/auth errors (401/403/404/409, certain 400 failures) require reconnection.
- The frontend records an in-memory session epoch and matches async callbacks to the current token. Late status/frame/inspection responses from a previous session are ignored, even when a prior browser tab still has in-flight requests. The token is never kept in localStorage or URL parameters.
- Only one screenshot request runs per HTTP polling chain; WebSocket frame production waits for explicit client consumption acknowledgement. The screenshot URL is revoked when replaced/closed and a hidden tab suspends polling; an abandoned server-side Page still expires under the 15-minute manager supervisor.
- Actions run through one ordered request queue (Socket.IO input when connected; HTTP fallback) (mouse down/move/up, key, resize and navigation); non-terminal input failures are reported without permanently blocking later commands. Drag capture loss sends a matching mouse-up when the session is still active.
- Actions are limited and validated: click, pointer move/down/up, wheel, selected keys, text (up to 512 chars), navigation, back/forward, refresh and viewport resize. URL and navigation requests go through the app's URL safety checks; popups are closed rather than being allowed to evade Page quotas.
- The UI tracks the displayed screenshot dimensions for accurate click coordinates; the manual Page viewport can be resized independently from other watch Pages.
- Authentication, CSRF, origin checks, per-login ownership tokens and restrictions on remote URL navigation protect the control API; keep server or Cloudflare Access controls as an additional layer. Do not expose Playwright/CDP, VNC or similar raw control ports publicly.

## Profile persistence: what can actually be verified

The host-mounted `browser-profile/` contains Chromium's `Default/Cookies`, `Local State`, `Preferences` and other state. A populated database proves data was written, **not** that a website login or human verification remains valid. The proper check: authenticate on a consenting test website in manual mode, close the manual Page, cleanly stop/restart the container, reopen the same website with shared mode, and verify the website itself still recognizes the session.

The container may write Profile files as UID 0. A host non-root user seeing `Permission denied` is expected for root-owned `Default/` with mode 700. Inspect with `sudo` when needed; do **not** recursively `chmod 777` or chown the active Profile. Back it up offline using [OPERATIONS.md](OPERATIONS.md).

## Limitations and future ideas (not implemented)

- This is JPEG image streaming over Socket.IO with HTTP polling fallback, not 30/60 FPS video, remote desktop, audio, or OS-window control.
- Popup-based sign-in flows may not work because untracked popups are closed.
- Human verification remains subject to target-site policies and may be requested again; no automatic CAPTCHA-solving guarantee.
- Xvfb + noVNC remain research options. An optional **experimental CDP Screencast** source now exists alongside the default Socket.IO JPEG screenshot producer and the HTTP fallback. CDP still delivers JPEG frames over Socket.IO, is not OS-level remote desktop/video, and has not been validated in the operator's live CloakBrowser deployment. Preserve the existing modes.

## Frontend verification after round 2 refactor

The browser interface is still **plain JavaScript**, without build tools or framework packages. `manual-browser.html` loads six local `defer` scripts in dependency order and a local CSS file. Update all six together when changing the shared module API; versions are cache-busted in the template. Do not import JavaScript directly from a CDN.

Run the frontend tests (Node 20+ recommended):

```bash
node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs
```

These tests use a simulated DOM and mocked same-origin HTTP API; they cannot substitute for real CloakBrowser tests. On the Docker host, validate initial connection, navigation/refresh, frame recovery after a temporary error, manual Page resizing, mouse drag release, URL synchronization, recovery/switch from a second tab, login ownership and authentication checks, and the watch-bound **完成并重新检查** action.

## Browser workspace UI (Product Extractors-aligned)

The Browsers page uses a compact dark interface with a unified header, status badge, address/navigation toolbar, action toolbar, large interactive viewport, and collapsible **文字输入** / **会话详情与使用说明** panels. Session recovery is displayed in a separate notice only when necessary. The visual language is aligned with Product Extractors while the screenshot remains the dominant, flexible-height area.

- The existing HTTP server API and the six JavaScript module boundaries are maintained. The template retains the existing element IDs consumed by `manual-core`, `manual-stream`, `manual-layout`, `manual-input`, and the entrypoint.
- `manual-layout.js` still measures the actual root offset and sizes the Page viewport to the screenshot container; compact headers and collapsed details leave more room for the interactive Page.
- The typing controls sit in a compact **always-visible single-row toolbar above the viewport**, with a deliberately width-limited text field. Keyboard events in the focused screenshot continue to work. Opening the session detail panel resizes the viewport when `ResizeObserver` is available.
- Styles remain scoped to `#manual-browser-root` in `static/manual-browser.css`. Feather icons already bundled with changedetection.io are used; no CDN or remote UI dependencies were added.

The JPEG-over-HTTP fallback, authentication, ownership checks, BrowserManager quotas, URL validation, 15-minute session expiration and watch recheck behavior have not changed. Test the UI with different screen heights, especially after expanding/collapsing the controls, resizing, navigating, and resuming a session.

## 2026-11: Browser input and frame responsiveness

- The **文字输入** toolbar is now a single non-collapsible row between navigation and the browser viewport. It has a bounded input width and quick Send, Enter and Backspace buttons. The viewport still fills all remaining available height.
- The footer keeps a lightweight Profile/idle indication; the collapsible **会话详情** presents browser generation, Profile lock, Cookie count for the current site, LocalStorage key count for the current origin, a separately wrapped URL, and split usage notes. Neither number is a count of accounts or storage size.
- `manual-input.js` notifies `manual-stream.js` once a remote action has completed. The stream prioritizes one screenshot after interaction, coalescing rapid operations and keeping at most one screenshot request outstanding in a given session. Navigation still suspends frames until the action completes.
- JPEG polling now adapts its delay: about **180ms** after recent interaction, **450ms** in normal use and **1000ms** after prolonged inactivity, *plus* network/screenshot/decode time. Browser tabs that are hidden still suspend polling. Transient errors preserve the earlier retry/backoff rules.
- The detail panel displays approximate frame HTTP round-trip, command completion time (including local queue wait), and observed frame display rate. These are diagnostic client-side observations, not guaranteed network or browser FPS benchmarks.
- Tests: `node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs` and `python -m unittest discover -s tests/cloakbrowser_shared -p test_manual_browser_workspace.py`. Check a real container to verify end-user latency and resource usage; faster polling can increase screenshot/CPU load.


## Viewport modes

The manual browser offers **fixed 1366×900 (default)** and **follow-window** modes; the selection is stored only in the operator browser localStorage (no session token). Fixed mode scales screenshots visually rather than resizing the remote Page on window resize. Follow-window resizes only the manual Page, not other Watch tabs.

## Shared desktop viewport and fixed-mode height

The desktop viewport size is configured via `CLOAKBROWSER_VIEWPORT_WIDTH` (default `1366`) and `CLOAKBROWSER_VIEWPORT_HEIGHT` (default `900`) in Compose. This size applies to scheduled shared Watch Pages, Product Extractors live Dry Run and manual fixed mode. Fixed mode adjusts only the manual Page when first connected or switching into fixed mode, and displays the JPEG at its original aspect ratio with a content-sized workspace to avoid tall empty bands. Follow-window mode instead uses the available WebUI canvas size and can change responsive page layout. Other Pages in the shared Context are unaffected by toggling the manual mode.

Both Browsers and Product Extractors use a shared, keyboard-operable themed dropdown. The native select remains the source of truth; the popup is placed outside scroll-clipping containers.

## 2026-11-05: WebSocket JPEG and input transport (Manual Input V2)

- The manual page prefers two authenticated Socket.IO namespaces, `/manual-input` and `/manual-frames`, using separate client Engine.IO connections so JPEG frames cannot queue in front of input messages. It remains a single Headless Chromium Page, with no new container or Profile writer.
- The input namespace enforces password-protected login, CSRF, matching Origin/Host, owner and browser generation. A single input controller is accepted; each command has a sequence and execution acknowledgement. Commands run through existing `ManualSessionManager.action` validations. Disconnected input releases any pressed mouse button.
- The frame namespace streams binary JPEG (quality 65) with a single frame outstanding until the client acknowledges decoding/consumption. Target intervals after capture are 100/200/500 ms (active/recent/idle), bounded by actual screenshot/transport/decode duration. Hidden/suspended views stop generating new frames after the in-flight image. Frames do not extend the 15-minute human idle timeout.
- The detail panel offers **自动 · WebSocket 优先** (default) or **仅 HTTP**, saved in localStorage without credentials. If WebSocket is disabled, unsupported by the reverse proxy, or drops unexpectedly, the client closes both channels and returns to the original HTTP input and JPEG polling. Unconfirmed commands must **never** be replayed automatically during fallback.
- Mouse Hover is forwarded; drag release flushes its last pending move before `up`. Existing keyboard controls are unchanged.
- The base template supplies the bundled Socket.IO client only when Socket.IO UI is enabled. `SOCKETIO_MODE=threading` remains preferred; check WebSocket upgrade support in the deployment proxy and confirm the page's **画面/输入** field reads `WebSocket` in a real browser.
- WebSocket does not promise Cloudflare verification success: Playwright/automated browsers may be rejected independently of pointer delivery.
- Real Docker/Chromium performance, authorization, websocket disconnect, and exact frame rates require on-host validation; local Node/unit tests are not end-to-end evidence.

## 2026-11-05: Frame diagnostics and browser environment

- The displayed FPS is a five-second sliding observation of **displayed frames**, not the inverse of a single pair of frame timestamps. The status refresh reports 0 after the most recent frame has gone stale. Idle streaming still intentionally reduces its frame cap; a low idle FPS alone is not proof of a transport bottleneck.
- Socket.IO frames contain server-side metrics `capture_ms`, `screenshot_ms`, `dispatch_ms`, and `bytes`. `screenshot_ms` measures the Playwright screenshot/encoding await within the BrowserManager loop; `dispatch_ms` is the remainder of the manager synchronous call (including scheduling and cross-thread completion), not an exact CPU or network metric. `capture_ms` is their approximate sum. `previous_ack_ms` is the server's send-to-ack elapsed duration, which includes network, client image consumption and scheduling; it is **not** one-way network latency. The frontend also shows image-load elapsed time (includes event loop scheduling; not a pure decoder benchmark).
- HTTP fallback continues reporting HTTP screenshot round-trip time, with Chromium-only/dispatch timings unavailable. Do not compare HTTP RTT with WebSocket `capture_ms` as though they measure the same thing.
- The transport preference select uses the existing `data-custom-select` enhancer. No second dropdown implementation or new JS framework was added. The native `<select>` remains the authoritative setting, including when changed with a keyboard.
- The details panel now displays the current manual Page's `navigator.userAgent`, `navigator.platform`, `window.innerWidth/innerHeight`, and `window.devicePixelRatio`, with a copy-UA action. These are page-observed values, not necessarily the raw on-the-wire User-Agent request header. Navigations can temporarily make JavaScript evaluation unavailable; absent values are displayed as unavailable, not invented. The shared backend is still configured as Headless.
- Benchmark WebSocket and HTTP on the same target Page and viewport in the actual deployment, separately under idle/scrolling conditions. This revision does not implement WebP, CDP Screencast, headful Chromium or video, nor guarantee a particular FPS or challenge outcome.

## 2026-11-05: Compact session details (UI V4)

- The collapsible session details now keep Profile/generation/cookie/storage counters, followed by a copyable actual URL, a three-metric performance overview (displayed FPS, frame response, input response), and optionally expanded detailed frame timings. The metric sources and five-second FPS calculation are unchanged.
- WebSocket/HTTP mode preference is grouped with the active transport and still uses the shared themed CDSelect. The multi-paragraph help is collapsed by default; neither help nor metric expansion affects the underlying Session or browser.
- Browser environment **displays only the live Page's full User-Agent and copy button**. Platform, viewport and DPR are intentionally no longer displayed; backend metadata fields are retained for compatibility. User-Agent is page-observed and is not necessarily the HTTP request header.
- The details panel uses compact spacing, responsive metric cards, and a scoped thin scrollbar. The URL and UA are rendered as text, never HTML; neither is automatically copied to another service.


## 2026-11-05: Experimental CDP Screencast frame source

- In **会话详情 → 画面引擎**, choose **WebSocket JPEG（默认）** or **CDP Screencast（实验性）**. This selection is stored in the operator browser's localStorage, not in the persistent Profile. Existing **传输偏好 → 仅 HTTP** remains available. Selecting CDP while HTTP is active switches transport preference to automatic WebSocket; losing the WebSocket connection still safely falls back to HTTP.
- The optional `changedetection_cloak_shared/manual_screencast.py` attaches an internal Playwright CDPSession to the already-leased manual Page (not a new browser). Frame events are Base64-decoded to bounded JPEG bytes, sent on the existing authenticated Socket.IO frame namespace, with an at-most-one-frame local buffer and existing client consumption acknowledgement. CDP `screencastFrameAck` is independent of the browser UI acknowledgement. Input is unchanged and remains on its own authenticated namespace.
- CDP creation, event callbacks and stop/detach run exclusively on BrowserManager's asyncio loop. Switching frame modes may recreate the *frame connection*, not the manual Page or its Profile. When CDP startup fails or no first frame arrives within five seconds, the frame producer falls back to WS JPEG without disconnecting mouse input. A static page may legitimately emit no *subsequent* CDP frames; last image is retained.
- Closing a manual session stops CDP before releasing the original Page lease. CDP cleanup failures must not block lease closure. Old stream cleanup uses a stream identifier so it cannot detach a newer CDP stream. The existing 15-minute session timeout is unaffected by frame events.
- Metrics: CDP does not use `page.screenshot()`, so screenshot/dispatch timing show `—` and frame response shows event-driven CDP rather than pretending to measure Chromium screenshot time. JPEG frame size and displayed FPS remain available. Switching engines retains the final image until the new frame arrives.
- For acceptance on the Docker host: test CDP first-frame delivery, scrolling and navigation, static pages, switching CDP ↔ WS JPEG, HTTP fallback, closing/resuming manual sessions, window/tab hiding, other Watch checks and repeated browser restarts. Measure actual CPU, memory, FPS and video smoothness; local mock tests **do not** establish CloakBrowser 0.7.0 compatibility or a performance improvement.

## 2026-11-05: Browsers UI V6 — context-aware actions and compact controls

- **完成并重新检查** is available only when the current Browsers page was entered with a valid Watch context **and** the owned manual session is associated with that same Watch. A generic sidebar Browsers page never displays the action, even if it resumes a session started by a Watch. Both open and resumed sessions now return their actual `watch_uuid` association; the `/api/finish` endpoint also rejects requests without an owned Watch-linked session **before** closing it. `/api/close` still ends general sessions without scheduling a Watch check. Deleted/paused/running Watches retain existing queue guards.
- The danger-styled **关闭会话** action now sits directly right of **连接浏览器**. The Watch-only finish action stays in the same navigation row. Redundant `实时交互画面 / 浏览器已连接` copy is removed; the top connection badge remains authoritative, while transient errors and switching feedback remain available.
- Viewport mode, frame engine, and transport preference now sit together in the upper operation toolbar. The existing custom-select implementation and transport/frame state IDs remain unchanged. Engine switch feedback is visible in the toolbar; the input/typing toolbar remains always visible, and no responsive toolbar redesign is included in this patch.
- The duplicate detailed URL panel and its copy button are removed. The editable top navigation field is now the single URL display; status updates synchronize it only while the user is not actively editing. Detailed performance, compact metrics, User-Agent copying and collapsed usage notes remain in the lower session details. Input-response milliseconds describe the latest completed operation (including navigation/wait), not continuous pointer latency; CDP has no `page.screenshot()` duration.
- The original shared Headless Context, Profile, HTTP/WebSocket JPEG, experimental CDP Screencast, input sequencing and 15-minute expiry are unchanged. Run front-end, template and manual-session tests; verify layout, Watch-context resume and real-browser mode switching on the Docker host.
