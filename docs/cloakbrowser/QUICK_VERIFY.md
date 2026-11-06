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
