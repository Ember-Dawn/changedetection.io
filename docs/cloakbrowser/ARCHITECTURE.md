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

`changedetectionio/blueprint/manual_browser/` exposes authenticated routes for session discovery, new Page, JPEG frame, status, input, finish and close. `changedetection_cloak_shared/manual_session.py` manages one human session with a token tied to a login session and browser generation; it uses a normal Page lease and has a 15-minute idle timeout. The main browser remains headless. There is no Xvfb/noVNC desktop and no public CDP port. See [MANUAL_BROWSER.md](MANUAL_BROWSER.md).

For shared scheduled fetches, `manager.py` uses a Page wrapper to inspect a loaded page for known Google/Cloudflare challenges **after the regular upstream wait but before normal XPath/HTML extraction**; failures propagate to Worker without committing challenge text as a normal change. Additional fallbacks and alert state handling are in `verification_alerts.py` and `worker.py`. See [VERIFICATION.md](VERIFICATION.md).

## Source map for review

- `integrations/cloakbrowser-shared/changedetection_cloak_shared/{manager,plugin,profile_manager,page_readiness,manual_session,backup}.py`
- `changedetectionio/blueprint/{browser_steps,add_watch_ui,manual_browser}/`
- `changedetectionio/{worker,worker_pool,verification_alerts,notification_service}.py`
- `changedetectionio/content_fetchers/playwright.py` for the persistent-context `viewport_size=None` screenshot fix.

There is no requirement to add another Docker container, another Chrome profile, or a separate browser service merely to provide a Page-level manual control UI.

## Backend maintenance round 1 (2026-11-03)

The manager retains ownership of its asyncio loop, generation, Profile lock, and all Page leases. `session_alive()` and `profile_lock_held()` are narrow read-only methods used by manual-session state; they do not expose Playwright objects to Flask threads. The upstream CloakBrowser 0.1.1 extraction wait hook remains the only automatic early-verification seam, isolated in `_check_verification_after_upstream_wait()` and covered by fake-Page tests. No remote-desktop streaming or second browser is introduced.
