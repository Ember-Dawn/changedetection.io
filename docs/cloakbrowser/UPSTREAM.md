# Upstream provenance, versions and compatibility boundaries

## What is pinned

`requirements-cloakbrowser.txt` currently pins:

```text
changedetection.io-cloak-browser==0.1.1
cloakbrowser==0.7.0
```

`Dockerfile.cloakbrowser` installs both packages with `--no-deps` to avoid replacing this fork of changedetection.io with its PyPI version. It also installs the local extension from `integrations/cloakbrowser-shared/` (`changedetection-cloak-shared`, currently `0.1.0`) and the required Python/browser libraries. The Dockerfile does **not** pin the actual downloaded CloakBrowser Chromium **binary** to a fixed version: the wrapper resolves a version separately. Operators should record `docker compose exec changedetection python -m cloakbrowser info` outputs when diagnosing upgrade regressions (omit licenses/secrets).

Important upstream repositories:

- changedetection.io: https://github.com/dgtlmoon/changedetection.io
- CloakBrowser adapter: https://github.com/dgtlmoon/changedetection.io-cloak-browser
- CloakBrowser wrapper/browser project: https://github.com/CloakHQ/CloakBrowser

This is **not** an official changedetection.io architecture; the local shared adapter is maintained by this fork. `html_cloakbrowser` remains the upstream isolated backend; `html_cloakbrowser_shared` is the fork's shared persistent backend.

## Compatibility shim that needs review

The external `changedetection.io-cloak-browser==0.1.1` fetcher imports `cloakbrowser.launch_async` **inside** `run()`. The local shared extension installs a process-wide router, conditioned by a `ContextVar` on BrowserManager's asyncio loop, that redirects this call to a non-owning lease of `launch_persistent_context_async(...)`. This avoids editing the installed upstream fetcher but **is coupled to its implementation**. Upgrading either package may alter imports, Playwright contracts, Context options, browser download/cache paths or Profile format. Do not auto-update without reviewing the actual new code and performing local tests.

The original GitHub `master` source of the external adapter was recorded during the initial investigation as `fetcher.py` blob SHA-1 `2ea0ef77d22514282caccfae50801139109a63b7` and `setup.py` blob `6f283dbc5962cd3a0cc34d8e31d9f7931e2dda87`. These are **historical provenance for the original integration**, not hashes of the fork's current edited files or a guarantee that `master` remains unchanged.

## Fork-owned areas and upgrade review

- Shared adapter implementation: `integrations/cloakbrowser-shared/changedetection_cloak_shared/`.
- Original application integrations: `changedetectionio/blueprint/browser_steps/`, `changedetectionio/blueprint/add_watch_ui/`, `changedetectionio/blueprint/manual_browser/`, `changedetectionio/worker.py`, `changedetectionio/worker_pool.py`, `changedetectionio/verification_alerts.py`, `changedetectionio/notification_service.py`, `changedetectionio/content_fetchers/playwright.py`, and application shutdown registration.
- Runtime: `Dockerfile.cloakbrowser`, `docker-compose.yml`, `.env.cloakbrowser.example`, `requirements-cloakbrowser.txt`.

Before merging upstream changedetection.io or upgrading packages, diff **each actual modified file** against the target revision. Test application startup, `html_cloakbrowser` original mode, shared mode, shutdown and Profile lock, queued/running cancellation, Browser Steps, Add Watch, manual input, error screens, Telegram alerts and cold backup/restore.

The source hashes in the initial round documentation under [`history/`](history/) only describe what was read back then. Newer edits and user-provided ZIPs supersede those exact file versions. There is no verified one-to-one Git commit mapping for every past AI-generated ZIP; do not fabricate it in change logs.
