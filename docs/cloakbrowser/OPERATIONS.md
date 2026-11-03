# CloakBrowser round 3: operations and cold backups

## Scope

Single container, shared persistent Profile. Round 3 adds fail-closed browser recovery, safer cancellation/quota handling, a cooperative Profile lock, and an **offline cold** backup/restore CLI. No remote desktop, multi-Profile support, or live backup API.

**The operator must test locally.** No cloud Docker/Chromium integration test was performed. An application crash, kernel crash, or `docker kill` can still cause an inconsistent Chromium Profile; do not rely on Profile persistence as your only copy of login-related data.

## Runtime

The root `docker-compose.yml` is the active configuration; run ordinary `docker compose` commands without `-f`. It uses `Dockerfile.cloakbrowser` and the existing `.env` file.

Before deployment, use `.env.cloakbrowser.example` as the reference. Copy it to `.env` only if absent; preserve existing credentials when updating. Host WebUI port defaults to `9901`, mapped to container port `5000` on `127.0.0.1`. Open `http://127.0.0.1:9901` on the Docker host; for access from another machine use SSH forwarding or a secured reverse proxy. The Compose file fixes `FETCH_WORKERS=3` and `CLOAKBROWSER_PROFILE_DIR=/browser-profile`; it forwards page concurrency and browser recovery values from `.env`.

```bash
# Apply the incremental payload to your repository and rebuild.
docker compose build --pull
docker compose up -d
docker compose logs -f --tail=150 changedetection
```

Shared backend remains `html_cloakbrowser_shared`; the author's original isolated backend remains `html_cloakbrowser`. Browser activity starts lazily. Changes to global proxy, User-Agent, or browser fingerprint require a browser restart, not in-place mutation.

New environment settings:

| Key | Default | Behavior |
| --- | --- | --- |
| `CLOAKBROWSER_RECOVERY_MAX_RETRIES` | `3` | Retries after ordinary launch errors; ambiguous startup timeouts fail closed |
| `CLOAKBROWSER_RECOVERY_INITIAL_DELAY` | `2` | Exponential delay seconds, capped at 60 |
| `CLOAKBROWSER_MAX_PAGES` | `3` | Concurrent shared Page permits |

The manager blocks a second managed process via `browser-profile/.changedetection.lock` (advisory Linux `flock`) and Chromium's own profile locking. Its browser generation increments only after a successful launch. When old Chromium cannot be confirmed closed, automatic restart is **refused**, avoiding a second writer on the Profile. Restart the container only after checking for lingering Chromium processes.

## Safe offline backup

1. Stop the application **and wait until it exits**:

```bash
docker compose stop
```

2. From the repository root, create a restricted backup directory and run a temporary container (service must remain stopped):

```bash
mkdir -p backups
chmod 700 backups
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups" changedetection \
  python -m changedetection_cloak_shared.backup backup --output /backups
```

The backup tool checks its cooperative lock, refuses unsafe symlinks/special files, writes a temporary `.tar.gz`, fsyncs it, then publishes the archive and a `.sha256` file. Backup **does not** copy any of the separate `datastore/` monitor records. Preserve `datastore/` independently.

3. Protect backup archives: the archive contains saved website sessions, local storage and possibly account secrets. Do not publish it or commit it to Git. Use encrypted at-rest storage.

4. Start the app again:

```bash
docker compose up -d
```

**Do not run the backup tool against a running Chromium**. The cooperative lock blocks the shared manager, but does not protect against unrelated Chromium processes or external scripts that ignore the lock.

## Offline restore

1. `docker compose stop`.
2. Independently preserve the current `browser-profile/` contents (including any data created since the last backup). Move its content into a separate protected directory; leave the mounted Profile path present but **empty**, except possibly `.changedetection.lock` and Chromium's stale Singleton* entries. Never delete a Profile just to recover a startup error without making a copy.
3. Verify the archive's `.sha256` against a trusted checksum (the tool also checks it).
4. Supply the **actual** archive path and independent 64-character checksum:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups:ro" changedetection \
  python -m changedetection_cloak_shared.backup restore \
  --archive /backups/cloakbrowser-profile-YYYYMMDDTHHMMSSZ.tar.gz \
  --sha256 YOUR_VERIFIED_64_HEX_DIGIT_HASH
```

5. Start the app. Validate website login, screenshot and browsing steps. Old Chromium Profile formats may not be compatible with an older browser binary; do not downgrade blindly.

The tool validates the archive and stages extraction before copying into the bind-mounted Profile. A failed file copy triggers rollback of paths created by that invocation, including a directory that was only partially copied. If rollback itself fails (for example, filesystem I/O errors), inspect the destination manually; never assume the previous Profile was restored automatically. This is **not** a hot/atomic transaction across a Docker bind mount.

## Local acceptance tests

- Normal shutdown and restart, then confirm test website login persists.
- Kill only a Chromium child/process; check logs for `RECOVERING`, generation changes, and active watch errors. Do not simulate corruption against your only valuable Profile copy.
- Cancel a slow watch; check another watch remains responsive and the active Page count decreases.
- Try opening the same Profile from a second changedetection process. It must refuse with a lock error.
- Stop the app, backup, verify `.sha256`, restore to a new empty test profile, and verify known test cookies/data.
- Verify that a failed Page.close does not silently release a permit and create a fourth Page above a configured max of three.
- Verify the old `html_cloakbrowser` standalone backend remains usable.

Python unit tests (no Chromium required, run locally if desired):

```bash
python -m unittest discover -s tests/cloakbrowser_shared -v
```

## Observability and limitations

`BrowserManager.status()` returns process-local state (`state`, `generation_id`, `active_jobs`, `reserved_slots`, `active_pages`, `closing_pages`, `preview_operations`, `profile_lock_held`, `context_alive`, `restart_count`, `last_error`, `uptime_seconds`). Do not start a second container to query it: that would observe a fresh manager, not the running application's state. A production admin endpoint/UI has not been added. Logs remain the primary diagnostics.

Any live WebUI preview session that spans a browser crash may need to be reopened. This round intentionally does not add automatic client-side session resurrection. Recovery is deliberately conservative: an unclosed former Chromium instance or ambiguous launch timeout results in FAILED rather than a second Chromium writing the same Profile.

## Reliability hardening (post-round-3 patch)

- All BrowserManager previews are registered while an operation runs; shutdown
  waits for/cancels operations before closing the shared Context. Idle preview
  browser-step sessions will be invalidated across generations and must be reopened.
- Registration of watch Futures is protected against the fast-completion race.
  Future cancellation is propagated to the manager event loop; the active task
  registry tracks ongoing cleanup after caller cancellation.
- A Page close that times out is still tracked as a background close; page permits
  are returned only when closure or loss of the old browser is confirmed.
- Docker shutdown now requests shared-manager drain *before* worker loops are
  forcibly stopped. This is not a fully graceful shutdown of other (non-shared)
  fetchers, which retain their upstream Worker Pool behavior.
- An ambiguous Chromium launch failure retains the Profile lock until the
  process exits. This is intentional to prevent unsafe concurrent Profile access.
  Inspect and terminate stray Chromium processes before restarting a FAILED
  container; do not delete Profile Singleton* lock artifacts blindly.
- Profile restore is still not an atomic transaction across a bind mount.
  Make an independent copy of an existing Profile before performing recovery.
- Shared profile options are validated before a Page is created; incompatible
  per-watch proxy/User-Agent values require the isolated backend.

### Additional local regression checks

1. Cancel a watch that has just been queued and one that is already running;
   neither may leave a permanent `active_jobs` entry.
2. Run browser-step preview while stopping the container. No new preview action
   should reopen the browser after shutdown begins.
3. Force a Page.close exception. Verify that it remains visible via
   `closing_pages`/`reserved_slots` and the manager invalidates its generation.
4. Use an intentionally interrupted *test* Profile restore (e.g. fill the
   destination volume mid-copy). A partially created destination must be
   removed when the filesystem permits rollback.
5. Try a symlink `browser-profile` or `.changedetection.lock`; the management
   tools must refuse rather than follow unsafe paths.

## Shared-browser page readiness and verification interstitial safety

`CLOAKBROWSER_PAGE_SETTLE_SECONDS` (default 2, 0-30) adds a short settling
delay for shared-browser visual preview and scheduled-watch extraction.
The original upstream fetcher already has its own extraction delay, including
the per-watch "Wait seconds before extracting text" setting.

If a recognized Google or Cloudflare verification interstitial is visible
during an Add Watch preview, the browser waits passively for at most
`CLOAKBROWSER_CHALLENGE_WAIT_SECONDS` (default 15, 0-90) additional seconds.
If the interstitial remains, preview returns HTTP 409 and does not save
temporary watch HTML or a misleading screenshot. It never clicks CAPTCHA
or attempts to bypass a site's checks.

For scheduled shared-browser watches, after normal extraction a conservative
HTML classifier raises `PageUnloadable` if the response is a recognized
verification interstitial. The worker records an error instead of committing
challenge text as a successful watch change. The longer challenge-specific
wait currently applies to preview only, not scheduled watches; use the
existing per-watch extract delay if necessary. Unfamiliar challenges may not
be detected; legitimate pages containing similar strings can rarely be
misclassified. Existing non-shared backends are unaffected.

Apply the incremental `payload/` files to the repository root, then rebuild:

```bash
docker compose build
docker compose up -d --force-recreate
```

## Manual browser: authenticated human operation (November 2026)

This extension adds **one** live interactive Tab in the **existing** shared
CloakBrowser Persistent Context. There is no second browser/container, no
exposed CDP/debugging port, and no automated challenge solver.

**Prerequisite:** set a changedetection.io application password and log in.
The `/manual-browser/` interface and all `/manual-browser/api/*` actions
intentionally return HTTP 403 if password authentication is disabled. They
use the existing Flask-WTF CSRF token; the GET frame/status routes also require
`X-CSRFToken` to prevent passive cross-site screenshot disclosure. Keep the
WebUI behind a trusted authenticated ingress (e.g. Cloudflare Access) as well.

Workflow, **new watch**:
1. Enter a URL in Add Watch, click **打开浏览器（人工操作）**.
2. In the new authenticated window, click **打开浏览器**, interact with the
   actual Tab with mouse/keyboard, then click **完成并重新检查**.
3. Return to Add Watch and click **前往 / Go** again for a fresh static preview.
4. Only save a Watch after the preview contains the expected content.

Workflow, **existing watch**:
1. Open the watch list or edit page; click **打开浏览器** for a Watch that uses
   `html_cloakbrowser_shared`.
2. Start the session; automated checks for *that Watch* are consumed instead
   of running while the operator controls it. Opening refuses a currently
   running watch; retry once the active check finishes. Other Watches can run.
3. Click **完成并重新检查** to close the manual Tab, release its slot, and queue
   one check through the existing priority queue (unless the Watch was paused
   by the operator). The Watch's original paused setting is never overwritten.
4. If the next check still detects a verification page, the last successful
   content stays intact and `last_error` remains visible. No verification
   success is promised.

Only one manual session can exist at a time. Inactivity automatically closes
its Page after 15 minutes. Frame polling does **not** count as operator activity.
The session is tied to the BrowserManager generation and becomes invalid if
that generation crashes or restarts. Any manual Page counts towards
`CLOAKBROWSER_MAX_PAGES` exactly like a normal watch Page. Popup windows
spawned by a website are closed automatically in this first version because
they are not yet tracked by the shared page quota; navigation inside the
original Tab remains interactive. Some popup-based login flows will therefore
need a future multi-page-aware implementation.

The small status bar shows current URL, *counts only* for cookies and
LocalStorage, Profile lock state, browser generation and session lifetime. It
never returns cookie values or tokens. A populated Profile alone does not
prove a website is still signed in; verify the session survives a clean
container restart using a legitimate test account.

**Security limitations:** Browser navigation requests are validated against
`is_fetch_url_allowed()`, including navigation triggered by page interactions.
This is a defense in depth, not a general guarantee against all forms of
browser-based SSRF or a third-party web page accessing internal resources.
Enable app authentication, never allow anonymous remote control, and avoid
exposing the browser management interface on untrusted networks. Remote
human interactions with third-party challenges must comply with their terms.

Rebuild after applying the incremental ZIP:

```bash
docker compose build
docker compose up -d --force-recreate
```

Local acceptance: open a test site, click/type/scroll, close and check that
`active_pages`/`reserved_slots` return to their prior values; verify existing
watch recheck, paused watch stays paused, 15-minute expiry, 2 simultaneous
open attempts (second should get HTTP 409), authentication/CSRF rejection,
and Profile persistence after normal Docker restart.
