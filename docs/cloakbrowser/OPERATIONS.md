# CloakBrowser round 3: operations and cold backups

## Scope

Single container, shared persistent Profile. Round 3 adds fail-closed browser recovery, safer cancellation/quota handling, a cooperative Profile lock, and an **offline cold** backup/restore CLI. No remote desktop, multi-Profile support, or live backup API.

**The operator must test locally.** No cloud Docker/Chromium integration test was performed. An application crash, kernel crash, or `docker kill` can still cause an inconsistent Chromium Profile; do not rely on Profile persistence as your only copy of login-related data.

## Runtime

```bash
# Apply the incremental payload to your repository and rebuild.
docker compose -f docker-compose.cloakbrowser.yml build --pull
docker compose -f docker-compose.cloakbrowser.yml up -d
docker compose -f docker-compose.cloakbrowser.yml logs -f --tail=150 changedetection
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
docker compose -f docker-compose.cloakbrowser.yml stop
```

2. From the repository root, create a restricted backup directory and run a temporary container (service must remain stopped):

```bash
mkdir -p backups
chmod 700 backups
docker compose -f docker-compose.cloakbrowser.yml run --rm --no-deps \
  -v "$PWD/backups:/backups" changedetection \
  python -m changedetection_cloak_shared.backup backup --output /backups
```

The backup tool checks its cooperative lock, refuses unsafe symlinks/special files, writes a temporary `.tar.gz`, fsyncs it, then publishes the archive and a `.sha256` file. Backup **does not** copy any of the separate `datastore/` monitor records. Preserve `datastore/` independently.

3. Protect backup archives: the archive contains saved website sessions, local storage and possibly account secrets. Do not publish it or commit it to Git. Use encrypted at-rest storage.

4. Start the app again:

```bash
docker compose -f docker-compose.cloakbrowser.yml up -d
```

**Do not run the backup tool against a running Chromium**. The cooperative lock blocks the shared manager, but does not protect against unrelated Chromium processes or external scripts that ignore the lock.

## Offline restore

1. `docker compose -f docker-compose.cloakbrowser.yml stop`.
2. Independently preserve the current `browser-profile/` contents (including any data created since the last backup). Move its content into a separate protected directory; leave the mounted Profile path present but **empty**, except possibly `.changedetection.lock` and Chromium's stale Singleton* entries. Never delete a Profile just to recover a startup error without making a copy.
3. Verify the archive's `.sha256` against a trusted checksum (the tool also checks it).
4. Supply the **actual** archive path and independent 64-character checksum:

```bash
docker compose -f docker-compose.cloakbrowser.yml run --rm --no-deps \
  -v "$PWD/backups:/backups:ro" changedetection \
  python -m changedetection_cloak_shared.backup restore \
  --archive /backups/cloakbrowser-profile-YYYYMMDDTHHMMSSZ.tar.gz \
  --sha256 YOUR_VERIFIED_64_HEX_DIGIT_HASH
```

5. Start the app. Validate website login, screenshot and browsing steps. Old Chromium Profile formats may not be compatible with an older browser binary; do not downgrade blindly.

The tool validates the archive and stages extraction before copying into the bind-mounted Profile. A failed file copy can leave a partial restore; on failure keep the preserved old copy, clear only files created by that failed restore, and retry when the underlying I/O issue is fixed. This is **not** a hot/atomic transaction across a Docker bind mount.

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

`BrowserManager.status()` returns process-local state (`state`, `generation_id`, `active_jobs`, approximate `active_pages_estimate`, `restart_count`, `last_error`, `uptime_seconds`). Do not start a second container to query it: that would observe a fresh manager, not the running application's state. A production admin endpoint/UI has not been added. Logs remain the primary diagnostics.

Any live WebUI preview session that spans a browser crash may need to be reopened. This round intentionally does not add automatic client-side session resurrection. Recovery is deliberately conservative: an unclosed former Chromium instance or ambiguous launch timeout results in FAILED rather than a second Chromium writing the same Profile.
