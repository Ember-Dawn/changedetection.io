# CloakBrowser operations: deploy, diagnose, back up and restore

## Active deployment

`docker-compose.yml` is the **active** Compose file. It builds `Dockerfile.cloakbrowser` and starts one `changedetection` service; do not use removed round-specific Compose examples.

```bash
cd ~/app/changedetection.io
mkdir -p datastore cloakbrowser-home browser-profile backups
chmod 700 cloakbrowser-home browser-profile backups
# If missing only: cp -n .env.cloakbrowser.example .env
# Edit .env to provide your valid CLOAKBROWSER_LICENSE_KEY.
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=150 changedetection
```

On Python/code changes rebuilt into the image: `docker compose build && docker compose up -d --force-recreate`. For updates to only external `.env` configuration: `docker compose up -d --force-recreate` may suffice. Avoid printing full environment/configuration publicly: it can contain the license key and session secrets.

| Setting | Source / current behavior |
| --- | --- |
| Host UI port | `CHANGEDETECTION_PORT` default **9901**, mapped `9901:5000` (all host network interfaces) |
| Service workers | Compose `FETCH_WORKERS=3` |
| Shared Page permits | `CLOAKBROWSER_MAX_PAGES` default **3**; watch/preview/manual Pages count |
| Profile directory | `CLOAKBROWSER_PROFILE_DIR=/browser-profile` in Compose |
| Browser license | `CLOAKBROWSER_LICENSE_KEY` from private `.env`; required |
| Browser recovery | `CLOAKBROWSER_RECOVERY_MAX_RETRIES` default 3; `CLOAKBROWSER_RECOVERY_INITIAL_DELAY` default 2 seconds |
| Original extraction delay | `WEBDRIVER_DELAY_BEFORE_CONTENT_READY` in upstream CloakBrowser fetcher and watch-specific delay; not removed |
| Retired waits | `CLOAKBROWSER_PAGE_SETTLE_SECONDS`, `CLOAKBROWSER_CHALLENGE_WAIT_SECONDS` no longer used by active shared-preview/fetch flow |

Compose mounts `./datastore:/datastore` (watches), `./cloakbrowser-home:/root/.cloakbrowser` (binary/cache) and `./browser-profile:/browser-profile` (site sessions). Protect all these and `./backups`. The published port now listens on all host network interfaces. LAN clients may connect via the server IP if network rules permit; Cloudflare Tunnel access depends on the cloudflared container network mode. Secure the endpoint with changedetection.io authentication and restrict ingress at the firewall/network edge. Docker port publishing may bypass simple UFW rules; verify the effective Docker/firewall policy rather than assuming the port is private. Application password authentication is **required** for manual browser controls; Cloudflare Tunnel routing alone does not remove this requirement.

## Diagnostics (no Profile changes)

```bash
docker compose ps
docker compose logs --tail=250 changedetection
docker compose exec changedetection python -m cloakbrowser info
sudo du -sh browser-profile
sudo find browser-profile -maxdepth 3 -type f \
  \( -name Cookies -o -name Preferences -o -name 'Local State' \) \
  -printf '%p (%s bytes)\n'
```

The `info` command distinguishes license validity, installed Chromium binary and resolved browser version. A `CLOAKBROWSER_LICENSE_KEY` environment variable being present is **not** proof it is valid. Chromium may be installed/downloaded separately from Python wheel upgrades. `ps` is not always installed in the slim image; an absent `ps` command is not evidence that Chrome stopped.

`BrowserManager.status()` has diagnostic fields such as state, generation, active jobs/Pages, closing Pages, reserved slots, Profile lock and last error, but it is **process-local**. Running a second temporary container will instantiate a different manager, not inspect the currently running one. Use application logs for production diagnosis; do not open a second writer on the Profile just to query its status.

When a browser launch times out or recovery enters FAILED, check for lingering Chromium processes before restarting. A conservative failure may keep the Profile lock; do not blindly remove `.changedetection.lock` or Chromium's Singleton files, and do not delete Profile data to make a launch pass. `browser-profile/Default` may be owned by container root with mode 700; inspect using `sudo` rather than recursively changing permissions.

## Safe offline Profile backup

This is a **cold backup**. Stop changedetection and wait for it to exit. Back up `datastore/` separately: the Profile backup CLI does **not** include watch records.

```bash
cd ~/app/changedetection.io
docker compose stop
mkdir -p backups
chmod 700 backups
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups" changedetection \
  python -m changedetection_cloak_shared.backup backup --output /backups
```

The tool rejects unsafe trees/symlinks and writes an archive plus `.sha256` file. The archive includes cookies and logged-in sessions: restrict access and use encrypted storage. Do **not** run backup against a live Chromium. The cooperative lock cannot defend against unrelated Chrome processes that ignore it.

```bash
# Restart application once backup finishes:
docker compose up -d
```

## Offline restore (high risk)

1. Stop the application: `docker compose stop`.
2. Preserve an **independent copy** of your current Profile first, then prepare an appropriately empty mounted Profile directory; do not overwrite valuable data in-place.
3. Verify the trusted archive's `.sha256` and obtain its actual 64-digit SHA-256 value.
4. Restore from the stopped-service temporary container (replace both placeholders):

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups:ro" changedetection \
  python -m changedetection_cloak_shared.backup restore \
  --archive /backups/cloakbrowser-profile-YYYYMMDDTHHMMSSZ.tar.gz \
  --sha256 YOUR_VERIFIED_64_HEX_DIGIT_HASH
```

5. Restart and confirm website sessions, screenshot and watch results. A newer Chromium Profile may be incompatible with a downgraded browser binary. Restore is not an atomic transaction across a bind mount: partial failures require inspection; the CLI attempts rollback of newly written paths, but filesystem failure can prevent cleanup.

## Local acceptance tests

- `python -m unittest discover -s tests/cloakbrowser_shared -v` in an environment with required Python dependencies. Do not interpret import errors as test success.
- With service stopped, `docker compose run --rm --no-deps changedetection python -m changedetection_cloak_shared.cli` validates manager navigation/JavaScript/screenshot, but it exercises a *separate process* and Profile writer. Never run this concurrently with the live service.
- Start 5+ watches with Page limit 3, confirm bounded simultaneous Tabs and that other fetcher backends still work.
- Check a manual session can resume after browser UI tab closure, navigate correctly, and release its Page when closed/expired.
- Check Add Watch screenshot speed and challenge-baseline protection; test Google/Cloudflare alert first detection, duplicate suppression, failed notification configuration and successful recovery.
- Log into a suitable test website manually, cleanly restart Docker and verify its session remains recognized. A Cookies file alone is not a sufficient persistence test.
- Stress cancellation/timeout on a *test profile*, not the only valuable user Profile. A timed-out Page close must not create an extra slot or second Profile writer.

See [ARCHITECTURE.md](ARCHITECTURE.md) for invariants and [VERIFICATION.md](VERIFICATION.md) for notification diagnosis.

## Verification notification troubleshooting (backend reliability round 1)

The watch's `manual_attention_reason` indicates an identified challenge. A separate `manual_attention_pending_token` means an Apprise notification is queued/in flight. Successful send acknowledgment writes `manual_attention_notified_reason`; sending failure clears pending and retries on the next eligible check after at least 5 minutes. Pending tokens left by a crash are retried after 10 minutes. Recovery uses corresponding `manual_attention_recovery_*` state and is only queued after successful watch processing.

For a missing Telegram message, verify effective watch/tag/global notification URLs and mute flags, the Notification debug log, and container logs for Apprise errors. The synthetic tests do not send external Telegram messages. Browser-manager compatibility and manual lifetime tests can be run on the Docker host with `python -m unittest discover -s tests/cloakbrowser_shared -v`.

## Round 2 frontend module deployment

After applying the incremental `payload/` ZIP, rebuild and recreate the service so Flask serves the new `manual-*.js` and `manual-browser.css` files. Refresh the browser tab with `Ctrl+Shift+R` after deploy (the manual template also has a static asset version parameter). No Profile reinitialization, Cookie deletion, BrowserManager worker-count change or new Docker service is needed. For frontend-only regression checks run:

```bash
node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs
```

This is a DOM/HTTP mock test, **not** a real Chromium test. A good local acceptance path is: open the global Browsers entry, log in, navigate two sites, perform a click/drag/scroll, resize the window, close and restore the manual tab, then verify that the scheduled monitors and Telegram/Apprise alerts remain operational.

## Desktop viewport settings

Edit the private `.env` to set `CLOAKBROWSER_VIEWPORT_WIDTH=1366` and `CLOAKBROWSER_VIEWPORT_HEIGHT=900` (defaults). Recreate the service after changing these values. Increasing height increases screenshot pixels and may make a fixed-size manual screenshot appear smaller on a short local display. Do not confuse viewport height with full-page screenshot height.
