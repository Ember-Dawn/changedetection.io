# Second round A+B: shared CloakBrowser architecture

## Scope and compatibility

The official `changedetection.io-cloak-browser==0.1.1` plugin is **not copied or edited**. It remains installed in the custom Docker image as backend `html_cloakbrowser` (isolated: one browser per check). The local extension in `integrations/cloakbrowser-shared` adds the separate backend `html_cloakbrowser_shared`. This deliberately preserves the complete original upstream extraction, screenshots, XPath, favicon, anti-bot handling and browser-step logic through subclassing. It also avoids maintaining a fork of a 16 KB upstream fetcher. The two backends are independently selectable per watch in Edit > Fetch.

**Implementation tradeoff:** the upstream fetcher imports `cloakbrowser.launch_async` inside its `run()` method. Because it does not expose a browser-factory injection point, this extension installs a narrowly scoped, process-wide router around `cloakbrowser.launch_async` and uses a Python `ContextVar` to choose the shared browser **only** for jobs executed on BrowserManager's dedicated loop. Calls without that flag delegate to the unmodified launcher. This is a deliberate compatibility shim, not an upstream feature. Recheck it whenever updating the original plugin or CloakBrowser. The router must never be used to manage an unrelated application's CloakBrowser session in the same process.

## Resource ownership

```
changedetection.io queue
   -> WorkerThread A/B/C (separate asyncio event loops)
       -> SharedFetcher.run (await a thread-safe concurrent Future)
           -> BrowserManager (one dedicated thread + asyncio event loop)
               -> one CloakBrowser launch_persistent_context_async(/browser-profile)
               -> per-task ContextLease and Page (max CLOAKBROWSER_MAX_PAGES)
                   -> upstream fetcher logic: navigate, steps, HTML, screenshot
               -> close only task Page/lease; retain Persistent Context
           -> return completed fetcher fields to worker
```

The `ContextLease` is an adapter for upstream's `browser.new_context()` call: it does not create a real isolated BrowserContext. Its `new_page()` allocates one Page on the shared persistent Context and applies per-page HTTP headers. `ContextLease.close()` and `BrowserLease.close()` release pages only; neither has permission to close the persistent Context. BrowserManager alone closes it on process shutdown. Upstream `quit()` remains untouched and idempotent.

Shared mode **does not** isolate cookies/localStorage/IndexedDB. That is intentional. It uses the same persistent profile/fingerprint seed for all shared watches. This can also let one site's logout or state-changing actions affect another watch.

## Browser Steps and add-watch previews

In the ordinary implementation, `browsersteps_live_ui` lives on a dedicated BrowserStepsEventLoop and assumes it owns an entire context/browser. Shared sessions instead run all live actions (start, goto/click, screenshots, cleanup) through BrowserManager's event loop. `browsersteps_live_ui` still sees the familiar `new_context()` interface, but receives a non-owning context lease. Its cleanup closes only the preview Page. Existing CDP and isolated CloakBrowser sessions continue on the original loop. The Add Watch visual selector's `/snapshot` preview has the same routing.

Main-program modifications are limited to the browser-steps loop dispatch, Add Watch snapshot dispatch, WorkerPool's cancellation forwarding, and a best-effort shutdown hook. Other built-in backends retain the old code path.

## Concurrency and cancellation

- One BrowserManager per Python process, initialized lazily. This design assumes the shipped single-process changedetection.io entrypoint. Multiple Gunicorn workers or replicas would create distinct browsers competing for the same Profile, and are **unsupported**.
- Semaphore defaults to 3 active pages. Preview pages count against the same limit; no separate preview reserve yet.
- Watch cancellation is propagated by `worker_pool.cancel_running_uuid()` before the original worker loop is forcibly stopped. BrowserManager tracks active futures by watch UUID and cancels only the corresponding shared jobs. Future completion callbacks prevent stale mappings when an old worker loop disappears.
- BrowserManager's stop is best-effort only. It is not yet a fully resilient browser-restart state machine. Robust crash recovery, cold backup and extended soak tests remain third-round items.
- Proxy must be configured globally through `CLOAKBROWSER_SHARED_PROXY`. Watches requesting different proxies fail explicitly; use `html_cloakbrowser` for different per-watch proxies.
- User-Agent is Profile-level. Per-watch mismatches fail explicitly and should use isolated mode. Do not inject contradictory User-Agent headers into shared sessions.

## Invariants for subsequent AI work

1. **Never** call `PersistentContext.close()` from a watch or preview.
2. Playwright objects only run on the manager loop. Worker fetchers should not expose their Page after `run()` completes.
3. Every successful page allocation must release exactly one Semaphore permit, including exceptions and cancellation.
4. Changes to plugin registration must preserve the original `html_cloakbrowser` fallback.
5. Shared profile must never be used by more than one browser process concurrently.
6. The extension depends on the original package's public `register_content_fetcher` and on its internal call to `launch_async`. Changing original plugin versions requires compatibility tests.

See README.md for deployment and runtime tests, and UPSTREAM.md for baseline source hashes.


## Round 3 reliability changes

The BrowserManager now distinguishes STOPPED / STARTING / RUNNING / RECOVERING / STOPPING / FAILED, tracks generations, validates connectivity before reusing the persistent Context, and refuses a second launch when an old context cannot be closed. Managed Page.close only releases a permit after it knows the Page is closed (or its generation was retired). The long-running job registry is removed from inside the underlying manager-loop task's finalizer, not immediately on cancellation of the worker-side concurrent Future. Shutdown first blocks work and cancels jobs, then closes the persistent Context and releases the advisory Profile lock. The lock sits **inside** the bind-mounted Profile so separate Docker processes can see it. This is not a replacement for Chromium's own lock. See OPERATIONS.md for cold backup and restore.
