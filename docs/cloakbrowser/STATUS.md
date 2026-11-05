# Implementation progress and acceptance status (2026-11-05)

This page is a **current-status handoff**, not a replacement for source inspection. Updated against the uploaded complete project and the successive V2–V6 incremental payloads. It describes code present in this checkout, **not proof that every feature has passed real Docker/Chromium acceptance**. Detailed implementation belongs in [ARCHITECTURE.md](ARCHITECTURE.md), [MANUAL_BROWSER.md](MANUAL_BROWSER.md), and the chronological [CHANGELOG.md](CHANGELOG.md).

## Current implementation

| Area | State in source | Acceptance caveat |
| --- | --- | --- |
| Shared browser and persistent Profile | Implemented: Headless CloakBrowser, BrowserManager asyncio ownership, bounded leased Pages, one Profile writer | Production concurrency, crash recovery and persistence require real-host acceptance |
| Manual session | Implemented: authenticated ownership, 15-minute inactivity expiry, resume/close, Playwright pointer/basic keyboard, Watch-specific finish guards | Real UI/browser acceptance remains necessary |
| Input transport (V2) | Implemented: separate protected Socket.IO input, ordered acknowledgements, HTTP fallback; pointer Hover and drag cleanup | No guarantee of CAPTCHA/Cloudflare passage; full keyboard/IME is not implemented |
| Image transport (V2) | Implemented: WebSocket binary JPEG by default, one-frame client acknowledgement, adaptive pacing; HTTP polling fallback retained | Actual FPS depends on page, host and network |
| Diagnostics (V3) | Implemented: five-second displayed FPS, screenshot/dispatch/client-display/ack metrics, full current-Page User-Agent | Metrics have different measurement scopes; they are not exact one-way latency |
| Manual workspace (V4, V6) | Implemented: compact detail cards, themed selects, UA only, upper toolbar engine/transport controls, no duplicate URL, red close button | Live visual and Watch context paths need acceptance |
| CDP Screencast (V5) | **Experimental / opt-in**: uses same manual Page and authenticated frame channel; fallback to WS JPEG | CloakBrowser 0.7.0 real CDPSession frame delivery, stability and FPS **not verified** in authoring environment |
| OS remote desktop | **Not implemented**: no Headed/Xvfb/noVNC, RDP or WebRTC video service | Do not call the JPEG/CDP view a native desktop |

## Current UI behavior

- Default picture source is **WebSocket JPEG**, with optional **CDP Screencast（实验性）**; authenticated **HTTP** remains a compatible fallback. Input is WebSocket/Playwright with HTTP fallback, independently of the chosen picture producer.
- **画面尺寸**, **画面引擎** and **传输偏好** live in the upper toolbar. The input/typing row is always visible; responsive-toolbar redesign and text-row collapsing were explicitly excluded from V6.
- Sidebar **Browsers** is general browsing: **完成并重新检查** must not appear there, even if it resumes a previously Watch-linked session. Watch-specific entry plus matching server-owned Watch association is required; **关闭会话** is a separate red action.
- Detail panel retains Profile/generation/cookie/storage counts, performance overview, expandable detailed metrics, and a copyable **full UA only**. The editable top address bar is the sole visible URL field.

## Tests and confidence

- V6 delivery reported frontend tests **22/22**, workspace/template tests **11/11**, plus syntax and ZIP checks. V5 delivery separately reported CDP fake-session tests **4/4**. These results are from the prior delivery checks, not freshly run real-browser benchmarks.
- Full manual-session Python tests were **not completed** during the V6 delivery because the authoring environment lacked `loguru`; do not label all Python integration tests passed.
- Live Docker, pinned CloakBrowser Chromium + CDPSession, actual HTTP/WS/CDP FPS, CPU consumption, Watch recheck behavior, and cross-tab recovery must still be tested on the deployment host.

## Recommended next verification

1. Rebuild and recreate the service after applying the complete ordered incremental payloads; keep `browser-profile/`, `datastore/`, and license/private configuration untouched.
2. Confirm sidebar vs Watch entry: finish action hidden/shown correctly, server rejects invalid finish; close action never submits a watch check.
3. Compare **WebSocket JPEG** and **CDP Screencast** on the same page while actively scrolling. Record displayed FPS, capture/ack times and CPU; verify CDP first-frame timeout and fallback. Then test HTTP compatibility.
4. Check manual token rotation/resume, disconnect while dragging, 15-minute idle expiry, browser restart/generation change, and simultaneous scheduled Watches.
5. Run `node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs` and `python -m unittest discover -s tests/cloakbrowser_shared -v` with all runtime dependencies installed; follow [OPERATIONS.md](OPERATIONS.md) for real-host tests.

## Separate open integration check

Product Stock & Price form/processor/API fields were reported aligned in the 2026-11-04 source audit. The earlier README assertion of *currently legacy fields* was stale; **stored legacy configuration migration, Watch/Tag override behavior and live end-to-end notifications remain unverified**. See [RESTOCK_AND_ALERTS.md](../product-extraction/RESTOCK_AND_ALERTS.md). Do not mark this as fully resolved without deployment testing.
