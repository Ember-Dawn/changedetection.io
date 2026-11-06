# Quick Verify (Telegram human verification)

## Flow

1. An acknowledged verification failure may enqueue a Chinese notification. Telegram-only endpoints use `telegram_html`; the product name links to the monitored URL and “打开人工验证” links to `{{base_url}}verify/{{watch_uuid}}`. Other Apprise transports receive plain text and the same Quick Verify URL.
2. `/verify/<watch_uuid>` uses the existing changedetection password / Flask-Login remember-me cookie. No additional access token or separate password. Authentication is still enforced on every manual browser API call; anonymous operation is prohibited even if other views are public.
3. When the Watch still has `manual_attention_reason`, Quick Verify checks the global manual session and opens that Watch in the existing shared CloakBrowser. On recovered watches it does not auto-connect. Existing sessions are never taken over; the same logged-in browser owner may resume its own same-Watch session.
4. The operator uses the lightweight screenshot viewer, tap, long press drag, two-finger scroll/pinch zoom, text input and navigation. The remote desktop viewport is not switched to a mobile device fingerprint. HTTP screenshot fallback is used; no separate WebSocket/CDP control implementation.
5. The “完成并重新检查” button uses the existing owned `/manual-browser/api/finish`. This schedules a Watch check when allowed and does not itself mark a verification resolved. “退出操作” closes without recheck. Closing the browser or locking the screen leaves the server session until its existing 15-minute idle timeout; reopening the page with the same login can resume it.

## Full WebUI management

The original Browsers / manual-operation page shows other-owner occupancy. A management-only button uses `GET /manual-browser/api/admin/session` then `POST /manual-browser/api/admin/terminate` with an opaque, randomly generated session identifier. The manager performs a compare-and-close check so a stale confirmation cannot terminate a replacement. The operation releases the Page, invalidates old controls, and **never** rechecks or clears Watch Health. Existing `close()` continues to enforce owner and token. These APIs require changedetection password authentication, CSRF protection and same-origin requests.

Because changedetection has a shared-password single-user identity, hiding management buttons from Quick Verify does NOT create a different authorization role. All authenticated users technically possess the same backend privileges. Strict separation needs distinct identities/authorization later.

## Security and practical notes

- Keep the WebUI behind Tailscale or an authenticated HTTPS gateway. Telegram URL carries Watch UUID only and is **not** an access token.
- The public/base URL must be reachable from the phone; Telegram's built-in WebView and the system browser may have independent login cookies.
- Mobile touch input and session persistence across lock/unlock require device-specific acceptance testing. Browser autoplay/background restrictions may suspend frame polling; the server session persists until its idle timeout.
- This lightweight viewer polls JPEG through the existing authenticated HTTP API and may be less fluid than the desktop WebSocket viewer. It does not spoof completion of complex challenges.
- Actual Telegram delivery, login redirect, session ownership after mobile sleep, and force-close while streaming must be validated in the user's deployed Docker environment.

## Test mode and Watch list entries

- From the Watch list, select **one** Watch and use the final cyan toolbar buttons: **人工操作** or **测试人机验证**. Multiple selections (including cross-page selections) disable both controls. A selected Watch must use `html_cloakbrowser_shared`; an off-page-only selection is deliberately not assumed to have a compatible backend.
- Row-level and inline manual-operation links are removed, while `manual_attention_reason` and ordinary error messages remain visible. Normal `人工操作` opens `/manual-browser/?watch_uuid=...&autoconnect=1` in a new tab.
- Test link: `/verify/<watch_uuid>?test=1` opens the existing Quick Verify viewer for a healthy Watch, without fabricating a verification failure. The server requires the same authenticated WebUI password and stored Watch UUID; test mode does not accept arbitrary destination URLs.
- Test sessions are marked **server-side** in `ManualSessionManager`. The `/api/finish` endpoint rejects any test session before closing or enqueueing a Watch; test mode's **结束测试** uses `/api/close`. Test mode never mutates Watch Health or sends a verification notification. It still navigates the real watched site and may affect its shared browser cookies/session.
- Both modes share the same global human session and management controls. Live browser mode, manual session ownership, CSRF and resource cleanup are unchanged. Test the real mobile interaction and session termination in Docker before treating those paths as production verified.

## Compact controls and mobile gestures (2026-11-06)

- Test and real verification **share the same layout**. The main action is `结束测试` (test: close-only) or `完成并重新检查` (real: finish/recheck); the secondary `退出操作` stays in place but is disabled in test mode. Test protection remains enforced on the backend.
- Navigation controls use small, labeled-for-accessibility Lucide icon buttons (Back, Reload, Fit). The Fit action resets screenshot zoom and both local scroll offsets.
- The remote screenshot keeps the original desktop viewport. Pinch changes the *local* image width from 1x to at most 4x, anchored on the fingers' midpoint. Two fingers translate the local screenshot viewport using its scroll offsets. Remote pointer coordinates come from the displayed image rectangle, so they account for local zoom and panning.
- Single-finger tap sends a remote click; holding for 300ms or moving beyond the touch threshold starts a serialized remote `down` → coalesced `move` → `up` drag. Pointer cancellation, lost capture, page hide and blur attempt to release the held remote mouse button. Core request ordering is retained.
- Two fingers **never** send remote wheel actions. On touch devices, a small overlay scroll-control toggles **remote scrolling mode**; one-finger swipes in this mode send remote wheel events. Desktop mouse wheel still scrolls the remote page; Ctrl+wheel zooms the screenshot locally. All these behaviors need real phone and CloakBrowser acceptance testing.
- Keep the current global manual session ownership, test-mode no-recheck behavior, password authentication and browser resource limits unchanged. Run `node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs tests/cloakbrowser_shared/test_quick_verify_touch.cjs` after touch edits.
