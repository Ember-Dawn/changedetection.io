# CloakBrowser, round 3 A+B (reliability and Profile operations)

This round adds **single-instance + multiple short-lived Tabs + shared on-disk profile** to the first-round one-container Docker image. The original dgtlmoon CloakBrowser backend remains available for isolated tasks.

**Execution status:** code compiled and fake-browser unit tests passed in the authoring environment. Docker is not available here. Real Chromium, plugin registration inside an image, live Browser Steps, multi-site logins and restart persistence must be verified on your own Docker host before moving existing production watches.

## Apply and build

Apply every file under this ZIP's `payload/` to your repository root. Retain first-round files. Verify that `requirements-cloakbrowser.txt` still installs `changedetection.io-cloak-browser==0.1.1` and the agreed CloakBrowser version, and do not add dynamic `EXTRA_PACKAGES` for the shared backend.

```bash
cp .env.cloakbrowser.example .env        # only if your .env does not already exist
# Keep your existing license key if .env already exists.
mkdir -p datastore cloakbrowser-home browser-profile
chmod 700 browser-profile cloakbrowser-home

docker compose -f docker-compose.cloakbrowser.yml build --pull
# Validate both original and new plugin registrations without starting Chromium:
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python -c "from changedetectionio.content_fetchers import available_fetchers; print(available_fetchers()); assert {'html_cloakbrowser', 'html_cloakbrowser_shared'} <= {k for k, _ in available_fetchers()}"
# Original isolated browser smoke test:
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python /app/scripts/cloakbrowser-smoke.py --browser
# New shared persistent browser smoke test:
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python -m changedetection_cloak_shared.cli
# Start service:
docker compose -f docker-compose.cloakbrowser.yml up -d
```

The first browser launch may download CloakHQ's precompiled Chromium and requires a valid `CLOAKBROWSER_LICENSE_KEY` and network connectivity. This is a third-party binary; the original plugin warns that it is not audited by its maintainer. Do not store important account credentials until you have evaluated the trust and security implications.

## Use the shared mode

In changedetection.io, open a watch -> Edit -> Fetch -> select **CloakBrowser - Shared persistent profile (experimental)**. The original **CloakBrowser - Stealth Chromium** entry remains independent/isolation mode. **Existing watches are not silently migrated.** First test a simple page, then a JS page, screenshots, Browser Steps, and a site requiring login.

Shared mode keeps **one persistent Chromium Context per Python process**. Each checking watch gets its own short-lived page, up to `CLOAKBROWSER_MAX_PAGES` in parallel. The page closes at the end of the check, while Cookies and other data survive in the mounted browser-profile directory. The browser starts lazily and stays running between checks.

**Manual login in round 2:** a Browser Steps preview operates against the same profile and can carry out navigations and form steps, but there is no complete interactive desktop or remote-control UI yet. That interface is a future round.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `CLOAKBROWSER_LICENSE_KEY` | required | Put in `.env` (never commit) |
| `CLOAKBROWSER_PROFILE_DIR` | `/browser-profile` | Bind mounted browser data directory |
| `CLOAKBROWSER_MAX_PAGES` | `3` | Maximum simultaneous shared pages, including previews |
| `CLOAKBROWSER_PREVIEW_TIMEOUT` | `180` seconds | Timeout for a single synchronous UI preview action |
| `CLOAKBROWSER_HUMANIZE` | `true` | Same CloakBrowser option as first round |
| `CLOAKBROWSER_SHARED_PROXY` | unset | One profile-wide proxy; per-watch mismatch is rejected |
| `CLOAKBROWSER_SHARED_USER_AGENT` | unset | Profile-wide UA only |

The Compose file maps `./datastore` for monitors, `./cloakbrowser-home` for downloaded Chromium and cache, and `./browser-profile` for cookies, LocalStorage, IndexedDB, history and profile fingerprint seed. The `.dockerignore` explicitly excludes all three directories, protecting secrets and reducing the build context.

These directories must be writable by the container user. Do not copy a Windows Chrome profile directly into the Linux container. Do not start two containers or Chrome processes against the same profile folder at once. The mounted profile contains valuable login secrets; secure it accordingly.

The Compose app port is bound to `127.0.0.1` by default as in round 1. Change to a secured reverse proxy when LAN/remote access is required.

## Acceptance checks

1. From the one-container image, verify both backend names appear.
2. Create 5+ shared-mode watches with `CLOAKBROWSER_MAX_PAGES=3`; observe one Chromium launch and at most 3 simultaneous monitoring pages. Note that normal short-lived Chromium subprocesses may spawn multiple renderer processes.
3. Check that an HTTP Requests watch and an original isolated CloakBrowser watch are unaffected.
4. Use the Browser Steps live preview on a shared-mode watch; verify it does not close the browser running other shared watches.
5. Create a watch via the Add Watch visual snapshot picker while selecting shared CloakBrowser. Verify navigation, screenshot and XPath extraction.
6. Log in to a test website via a shared profile page; verify a separate shared watch sees the same cookie state. Stop the service cleanly, start it again and check whether the website's session remains valid.
7. Cancel a shared-mode watch from the queue while another shared-mode watch is running; the other watch should not be interrupted.
8. Confirm data was created in `browser-profile` on the host.

If these fail, select the original `html_cloakbrowser` backend as a safe rollback for affected watches. Do not delete the persistent Profile folder to fix startup issues without making a cold backup first.

## Diagnostics

```bash
docker compose -f docker-compose.cloakbrowser.yml logs --tail=200 changedetection
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python -m cloakbrowser info --quick
# Unit tests from the repository root on a Python host with deps installed:
python -m unittest discover -s tests/cloakbrowser_shared -v
```

## Known limitations at the end of round 2

- No real Docker/Chromium integration test has been run in this assistant environment.
- The launcher adapter relies on an upstream implementation detail and must be reviewed on upstream upgrades.
- Browser restarts after crashes, slow cancellation hardening, Profile cold backup, process health checks and manual full-visual browser control remain future work.
- A single persistent Context means shared cookies and site storage. Watch-specific proxy and UA changes cannot safely be applied to that session.
- Multiple changedetection.io application processes are unsupported with the same Profile.


## Third round additions

Round 3 adds browser-generation fault handling, safer Page quota semantics, cancellation cleanup tracking, conservative fail-closed recovery, an on-disk cooperative Profile lock and an offline backup/restore CLI. See [OPERATIONS.md](OPERATIONS.md) for commands, limitations and local tests. Manual visual browser control remains out of scope.
