# CloakBrowser implementation and acceptance status (2026-11-06)

This page tracks the **current repository implementation** and evidence supplied by the Docker operator. It is not a full production sign-off. For architecture and operation consult [ARCHITECTURE.md](ARCHITECTURE.md), [MANUAL_BROWSER.md](MANUAL_BROWSER.md), and [OPERATIONS.md](OPERATIONS.md). The historical sequence remains in [CHANGELOG.md](CHANGELOG.md).

## Current features

| Area | Implementation | Evidence / remaining limits |
| --- | --- | --- |
| Shared CloakBrowser | BrowserManager-owned persistent Profile, bounded Page leases; Headless Watch checks | Independent Profile persistence demonstrated; full concurrency and crash recovery not exhaustively tested |
| 截图操控 / Screenshot control | Authenticated manual Page with ordered Socket.IO input, JPEG frames and HTTP fallback; V6 Watch-only finish guard, compact toolbar and diagnostics | Existing UI tests; Cloudflare passage and all keyboard/IME cases not guaranteed |
| CDP Screencast V5 | Optional experimental JPEG producer on the same Page, fallback to WebSocket JPEG | Real CloakBrowser 0.7.0 CDP frame/FPS acceptance still open |
| 实时浏览器 / Live Browser V1 | Exclusive Headed mode with Xvfb, x11vnc, noVNC and protected WebSocket relay; temporarily pauses Watch admission, reuses same Profile, restores Headless | **Operator demonstrated working integrated noVNC display** after handshake fix; abnormal failure recovery and real Watch-load drain remain to test |
| Live Browser UI V7 | Shared **截图操控 / 实时浏览器** tabs, no enclosing pale card, proportional desktop display; explicit start/restore confirmation | Operator screenshots demonstrated the new UI; do not treat tab selection as an actual mode change |
| Live Browser geometry V8 | `xdotool` best-effort move/resize of the Headed Chromium X11 window to 1366×900, with diagnostics and safe warning on failure | **Operator explicitly confirmed bottom black bar is resolved** on Docker |

## What the operator verified on Docker

1. CloakBrowser **0.7.0** can launch/close Headed under Xvfb. A **separate temporary Profile** reopened Headless with persistent Cookie and LocalStorage values.
2. Standalone Xvfb + x11vnc + noVNC displayed Chromium; operator reported working mouse/keyboard, reconnection and graceful shutdown.
3. Initial integrated noVNC connection failed with `/manual-browser/live/ws` HTTP **400**; after the Werkzeug WebSocket route (`websocket=True`) correction, the operator showed the live Chromium page inside Browsers.
4. V7 rendered the compact mode tabs and unframed desktop. V8 added X11 window sizing; the operator reported **the bottom black strip is gone**.

These observations do **not** establish website-specific login persistence, Cloudflare verification success, exhaustive security testing or all error paths.

## Current UI and invariants

- **截图操控** normally uses WebSocket JPEG, with optional experimental CDP Screencast and HTTP fallback. It retains the always-visible text input toolbar and Watch-only **完成并重新检查** safety checks.
- **实时浏览器** is mutually exclusive with Headless screenshot control. Selection of its tab does not start a browser: **启动实时浏览器** and **结束并恢复监控** explicitly control the transition. While Headed is active, screenshot controls are unavailable.
- BrowserManager remains the **single owner of the Profile**; never run Headed and Headless simultaneously against `browser-profile/` or directly expose VNC/CDP ports. The maintenance gate must not silently change the user's existing `all_paused` preference.
- `xdotool` geometry fitting is best-effort and diagnostic; the noVNC framebuffer is not artificially cropped.

## Still to validate

1. Watch scheduler and Worker maintenance gate under **active and queued** Watch jobs; correct resumption without phantom checks, altered last-check timestamps or changed `all_paused`.
2. Failed/aborted start or restore, container restart mid-Live, Profile lock protection and session ownership/security negative cases.
3. Reverse proxy HTTPS/WSS WebSocket upgrading if this deployment uses a reverse proxy; test authentication and CSRF enforcement in that configuration.
4. Normal screenshot-control multi-Page concurrency and V5 experimental CDP stability/FPS; actual CPU and latency measurements.
5. Target websites' session retention after switching back to Headless; browser storage persistence alone is not a guarantee.

## Other project open work

Product Stock & Price form/processor/API fields were found aligned in the 2026-11-04 source audit; stored legacy configuration migration and live notification delivery remain unverified. See [RESTOCK_AND_ALERTS.md](../product-extraction/RESTOCK_AND_ALERTS.md).

### 2026-11-05 — Reliability patch status

The Watch Health reliability implementation was syntax-checked and pure state-machine
unit tests were added. Browser end-to-end testing and Telegram delivery verification
still require the operator's dependency-complete Docker host; do not describe those
as accepted until they have been exercised there. See `docs/watch-health/ARCHITECTURE.md`.

## 2026-11-06 — Health, Quick Verify and cleanup status

- Unified Watch Health now owns ordinary network and product-rule operational
  failures, with Chinese Telegram HTML notices and acknowledged incident IDs.
  Stock/price business notices remain separate. Standalone product-rule failure
  alerts have been retired (no migration of old datastore state).
- Quick Verify has a shared two-row toolbar on desktop/mobile: text + Send/Enter
  + wheel-up/wheel-down, followed by Back/Reload/Fit + session controls. Its
  screenshot is display-only; the viewport handles touch input. Native Via
  browser-owned menus may still require device-specific verification.
- Classic bulk Watch operations remain the original `changedetection.io(8).zip`
  flow. Known possible Request Context / Socket.IO rebinding issues were **not**
  changed in this documentation/style/test cleanup, by operator request.
- Offline syntax and mock/contract tests do not prove actual Docker, Telegram,
  multi-destination Apprise delivery, or Android/Via acceptance. Check the
  accompanying CHANGELOG for exact test commands and results.
