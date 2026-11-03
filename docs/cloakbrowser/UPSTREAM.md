# Upstream provenance and local changes

## Application baseline

This round was built against the full original uploaded `changedetection.io.zip`, not reconstructed from snippets. Existing source files changed here were read **in full** from the ZIP; original Git blob SHA-1 values (`git hash-object --stdin`) before modification:

| Original repository path | Original Git blob SHA-1 |
| --- | --- |
| `changedetectionio/blueprint/browser_steps/__init__.py` | `1d446504265cf6adde1a88810f7f97fba1810145` |
| `changedetectionio/blueprint/add_watch_ui/__init__.py` | `0a7ff0c55a9f4f4b267c574587bfc2c806d9247c` |
| `changedetectionio/worker_pool.py` | `573f6ad427a299572fee121314c0f066749c2915` |
| `changedetectionio/__init__.py` | `33e7c45de78db7b51609f673925624fc400473ed` |

The original `.dockerignore` was also read in full from the upload. Dedicated Docker/Compose files come from the first-round ZIP, **not** GitHub source files.

## Original author's plugin

- Repo: https://github.com/dgtlmoon/changedetection.io-cloak-browser
- PyPI distribution: `changedetection.io-cloak-browser==0.1.1` (first round)
- Original `changedetection_cloak_browser/fetcher.py` on repo `master` has published blob SHA `2ea0ef77d22514282caccfae50801139109a63b7` (GitHub API at investigation). `setup.py` blob `6f283dbc5962cd3a0cc34d8e31d9f7931e2dda87`.
- The full upstream Python plugin is installed by pinned PyPI dependency and **left unmodified**. Local extension subclasses the original registered Fetcher. No plugin source files were rewritten from partial web content.
- Important coupling: original `fetcher.run()` imports `cloakbrowser.launch_async` *inside* the function, which the local extension intercepts with an opt-in ContextVar router in manager loop. Check this before upgrading dgtlmoon plugin.

## Browser wrapper

- Repo: https://github.com/CloakHQ/CloakBrowser
- CLI/API: `launch_persistent_context_async(profile, ...)` and `BrowserContext.new_page()`
- Package version stays pinned by `requirements-cloakbrowser.txt` from round 1. The actually downloaded Chromium binary needs to be recorded after a real deployment (`python -m cloakbrowser info`).

## Modification boundaries

- New extension: `integrations/cloakbrowser-shared/` with its own pluggy entrypoint; original `html_cloakbrowser` is retained.
- Main app: small adapter changes in browser-steps, Add Watch snapshot, worker cancellation and shutdown hook. Other fetchers untouched.
- Docker: install local package without pulling a second PyPI changedetection.io, mount separate persistent profile, exclude it from build context.

No files were moved, renamed, or deleted in this round.


### Round 3 A+B

No changes to original dgtlmoon `changedetection.io-cloak-browser` package or CloakHQ browser source. Local shared adapter adds state transitions, ProfileLock and offline backup. The extension still depends on the upstream 0.1.1 fetcher's `launch_async` import behavior. Do not assume advanced auto recovery is safe if the old Chromium cannot be confirmed shut down; conservative FAILED behavior is intentional. The user runs real Docker/Chromium tests locally.

## Post-round-3 stability corrections

The original dgtlmoon CloakBrowser plugin remains unchanged. Changes only
harden the shared addon and two application integration paths. No new
mandatory third-party runtime dependency was introduced. Keep the upstream
`launch_async()` routing compatibility check on all future plugin upgrades.
The shared manager's Future registration/close callback behavior and Profile
cold restore rollback must be re-reviewed when changing asyncio or Chromium.
