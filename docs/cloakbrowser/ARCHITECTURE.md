# Shared CloakBrowser architecture and invariants

## Backends and ownership

The installed third-party `changedetection.io-cloak-browser` package contributes `html_cloakbrowser` (independent fetch/browser lifecycle). The local `integrations/cloakbrowser-shared/` package contributes `html_cloakbrowser_shared`. The shared `SharedFetcher` subclasses the original fetcher, running its coroutine on the dedicated BrowserManager asyncio loop. A scoped `ContextVar` launcher route intercepts the upstream's in-function `cloakbrowser.launch_async()` call and supplies non-owning Browser/Context leases around the single persistent Context. **This depends on an upstream implementation detail; see UPSTREAM.md.**

```text
changedetection.io scheduler -> FETCH_WORKERS (default 3)
  -> SharedFetcher.run -> BrowserManager (one event-loop thread)
       -> one launch_persistent_context_async('/browser-profile')
       -> _ContextLease -> _ManagedPage for each scheduled check
       -> separate _ManagedPage for visual preview or Browser Steps
       -> separate _ManagedPage for manual control (at most one manual session)
       -> close Page / release permit; retain persistent Context/Profile
```

BrowserManager, not worker/watch/UI code, owns the Context. Page and Context leases hide Context ownership from the original upstream fetcher. `ContextLease.close()` is **not** an instruction to close the persistent Context. Browser Steps and Add Watch preview dispatch onto the same BrowserManager loop in shared mode; non-shared fetchers use their existing paths.

## Page concurrency and browser process count

`CLOAKBROWSER_MAX_PAGES` defaults to **3** permits; `FETCH_WORKERS` is **3** in Compose. These are separate limits: a worker may wait for a Page. Each active shared check uses its own short-lived Tab (not one universal Tab reused serially). Once a check completes, its Page closes; the next check may use a new Page in the **same** Context. Add Watch visual preview and human control also consume Page permits. This is **one shared BrowserContext**, but Chromium still creates multiple internal renderer/utility OS processes; never equate one browser instance with one PID.

The browser is lazy: no session is launched until needed. Profile data (`Cookies`, localStorage, IndexedDB, etc.) persists under `browser-profile/`; web sessions may still expire on the remote site. All shared Pages intentionally share website state. The standalone `html_cloakbrowser` backend is not a participant in this shared Page pool and may launch another browser session.

## Async and cancellation invariants

1. Playwright Page/Context methods are called **only** on the BrowserManager loop. Flask and Worker loops must use manager dispatch methods.
2. Every acquired Page permit is returned exactly once, only when Page closure is confirmed or its browser generation has been retired. A timed-out close cannot falsely free a slot.
3. An unrecoverable/ambiguous launch failure must fail closed, **not** create another Chromium process writing the same Profile. A Profile advisory `flock` and Chromium's own lock are defenses, not a license to bypass a stale process.
4. BrowserManager tracks active job Futures by Watch UUID for cancellation, tracks preview operations for shutdown, and uses browser generation numbers to invalidate stale leases.
5. Global proxy/User-Agent are effectively Profile-wide. Per-watch settings incompatible with the shared context should fail rather than silently changing another watch's network identity.
6. Do not run multiple application processes/replicas against one `browser-profile/`. The current design is one BrowserManager **per Python process**.
7. Preserve the original independent backend on upgrades; do not patch its package as a shortcut to add shared features.

## Reliability lifecycle

The manager has a guarded launch/recovery state machine (`STOPPED`, `STARTING`, `RUNNING`, `RECOVERING`, `STOPPING`, `FAILED`), a generation counter, close/cancel tracking, and a ProfileLock in the bind-mounted directory. A new generation should be created only after it is safe to retire the previous one. Profile lock retention after an ambiguous launch timeout is intentional. Normal shutdown drains manager jobs, releases the Context and lock. Forced shutdown or host crashes can still leave Profile files in an inconsistent state; use cold backups.

## Manual browser and verification flow

`changedetectionio/blueprint/manual_browser/` exposes authenticated routes for session discovery, new Page, JPEG frame, status, input, finish and close. `changedetection_cloak_shared/manual_session.py` manages one human session with a token tied to a login session and browser generation; it uses a normal Page lease and has a 15-minute idle timeout. The scheduled Watch browser is Headless in normal operation. Live Browser temporarily runs the same Profile in Headed Xvfb with a protected noVNC desktop; neither raw VNC nor CDP is publicly exposed. See [MANUAL_BROWSER.md](MANUAL_BROWSER.md).

For shared scheduled fetches, `manager.py` uses a Page wrapper to inspect a loaded page for known Google/Cloudflare challenges **after the regular upstream wait but before normal XPath/HTML extraction**; failures propagate to Worker without committing challenge text as a normal change. Additional fallbacks and alert state handling are in `verification_alerts.py` and `worker.py`. See [VERIFICATION.md](VERIFICATION.md).

## Source map for review

- `integrations/cloakbrowser-shared/changedetection_cloak_shared/{manager,plugin,profile_manager,page_readiness,manual_session,manual_screencast,backup}.py`
- `changedetectionio/blueprint/{browser_steps,add_watch_ui,manual_browser}/`
- `changedetectionio/{worker,worker_pool,verification_alerts,notification_service}.py`
- `changedetectionio/content_fetchers/playwright.py` for the persistent-context `viewport_size=None` screenshot fix.

There is no requirement to add another Docker container, another Chrome profile, or a separate browser service merely to provide a Page-level manual control UI.

## Backend maintenance round 1 (2026-11-03)

The manager retains ownership of its asyncio loop, generation, Profile lock, and all Page leases. `session_alive()` and `profile_lock_held()` are narrow read-only methods used by manual-session state; they do not expose Playwright objects to Flask threads. The upstream CloakBrowser 0.1.1 extraction wait hook remains the only automatic early-verification seam, isolated in `_check_verification_after_upstream_wait()` and covered by fake-Page tests. No remote-desktop streaming or second browser is introduced.

## Manual UI modules and Socket.IO transport (2026-11-05)

The authenticated `/manual-browser/api/` HTTP routes remain available for session lifecycle, status and compatible fallback. The six local JS files load in order: `manual-core.js`, `manual-transport.js`, `manual-stream.js`, `manual-layout.js`, `manual-input.js`, `manual-browser.js`. `manual-core` owns the session token/epoch and one ordered command queue; `manual-transport` owns two dedicated Socket.IO connections (input and binary JPEG); `manual-stream` manages both frame consumption and HTTP polling fallback; input/layout/entrypoint retain their prior responsibilities. There is no additional browser or Persistent Context.

The two namespaces are registered from `realtime/socket_server.py` via `manual_socket.py`. Every connection validates password-protected login, CSRF, same-origin, owner token and browser generation before accepting commands or screenshot delivery. Input has sequential ACKs and uses the existing `ManualSessionManager.action()` URL/key/coordinate limits. Shared input locking prevents competing HTTP and WS mutation calls from executing concurrently. A disconnected controller releases any remote mouse button held down. Frames are JPEG byte attachments with one-frame-at-a-time client consumption ACK; a slow client does not accumulate queued snapshots. The frame producer never touches `last_active` and is stopped after session expiry/disconnect.

HTTP remains a failover path on missing/disabled Socket.IO, rejected WebSocket upgrade or socket failure, and is not an automatic replayer of unconfirmed events. Screenshots and input can continue through HTTP while the websocket transport is not active. An **optional experimental CDP Screencast** producer is implemented for the same leased manual Page; it sends JPEG frames via the existing authenticated Socket.IO channel and does not change input transport. CDP compatibility with live CloakBrowser is unverified. Separately, **Live Browser** offers an OS-level Xvfb/noVNC desktop during its exclusive Headed maintenance mode; screenshot control remains a separate Headless feature.


### Experimental manual CDP frame producer (2026-11-05)

The optional CDP Screencast path only changes how the *existing* manual Page produces JPEGs. `ManualScreencast` owns a Playwright CDPSession on BrowserManager's asyncio loop, acknowledges every valid CDP frame ID, and keeps at most the most recent waiting JPEG. The existing authenticated `/manual-frames` Socket.IO channel supplies network backpressure and `/manual-input` continues independently. The manual Page lease, shared persistent Context and single Profile writer do not change. Stream-specific identifiers prevent an old viewer teardown from stopping a replacement producer. CDP failures revert to the original WS screenshot implementation, and WebSocket failures revert to HTTP. This interface is experimental until confirmed against the pinned CloakBrowser runtime; no debugging port is exposed.

## Live Browser V1–V8 (2026-11-05; partial Docker acceptance)

`changedetectionio/live_browser_gate.py` is a process-local worker admission/drain gate; it does **not** mutate `all_paused` and does not persist. Existing worker jobs are requeued unchanged during maintenance. Manual/preview admission is refused. BrowserManager's manager-loop `_switch_live_mode` closes the previous Context before it reopens the **same** Profile in the new mode; the manager's `ProfileLock` is retained, and `stop()` remains the application shutdown method.

`changedetection_cloak_shared/live_browser.py` starts/stops Xvfb+x11vnc only during Headed operation. VNC binds container loopback; Flask's `/manual-browser/live/ws` WebSocket relay performs session, CSRF and same-origin checks, and assets are authorized per request. No 5900/6080 host mapping or standalone unauthenticated websockify listener is required. The integrated WebSocket route now declares `websocket=True`: the operator observed successful in-app noVNC rendering after an initial HTTP 400 handshake failure. This confirms the tested direct Docker access path, **not** every HTTPS reverse-proxy/WSS configuration. V7 removes the outer bordered Live card and introduces mode tabs. V8 installs `xdotool` and best-effort moves/sizes the actual Chromium X11 window to the 1366×900 Xvfb screen; the user confirmed the prior bottom black strip is gone. Geometry fitting logs warnings if it fails and does not crop noVNC coordinates.
