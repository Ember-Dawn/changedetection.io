# CloakBrowser integration: current status and documentation

This fork packages changedetection.io and CloakBrowser **in one Docker service**. Its optional local backend, `html_cloakbrowser_shared`, reuses **one persistent Chromium BrowserContext** and opens short-lived Pages/Tabs for monitoring tasks. A protected human-control UI can operate an additional Page using the same on-disk Profile. The upstream independent CloakBrowser backend, `html_cloakbrowser`, is retained separately.

**Documentation policy:** This README and the linked topic documents describe the *current intended implementation*. Files under [`history/`](history/) document earlier patches and may describe behavior that has since changed. When there is disagreement, inspect the current source.

## Documentation

| Read | For |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | BrowserManager architecture, event loop, Page/Tab concurrency and lifecycle |
| [MANUAL_BROWSER.md](MANUAL_BROWSER.md) | Login protection, interactive browser, recovery and session ownership |
| [VERIFICATION.md](VERIFICATION.md) | Google/Cloudflare challenges, watch states, Apprise/Telegram and limitations |
| [OPERATIONS.md](OPERATIONS.md) | Docker deployment, troubleshooting, safe Profile backup/restore and test checklist |
| [UPSTREAM.md](UPSTREAM.md) | Exact dependency pins, upstream coupling, modification boundaries |
| [CHANGELOG.md](CHANGELOG.md) | Historical sequence of implementation milestones |
| [history/](history/) | Archived round/incident documents; reference only |

The repository root [`AGENTS.md`](../../AGENTS.md) is the recommended starting point for a future AI maintainer.

## Current at a glance

- `docker-compose.yml` builds `Dockerfile.cloakbrowser`; host HTTP port defaults to `127.0.0.1:9901` and container port `5000`.
- Python package versions are **pinned** (`cloakbrowser==0.7.0`, `changedetection.io-cloak-browser==0.1.1`). The CloakBrowser-managed Chromium binary is version-resolved/downloaded separately; check the running version using `python -m cloakbrowser info`.
- Shared context Profile is bind-mounted at `./browser-profile:/browser-profile`. Binary/cache data is separate: `./cloakbrowser-home:/root/.cloakbrowser`. Watch settings and history are under `./datastore:/datastore`.
- `FETCH_WORKERS=3` and default `CLOAKBROWSER_MAX_PAGES=3`. Each concurrent shared fetch leases **its own** Page, up to the available Page limit; queued checks wait. Pages close after checks, while the Profile/Context survives. A manual browser Page also consumes one permit.
- The manual browser is reachable at **Browsers** in the sidebar and from relevant Add Watch / existing Watch entry points. It uses actual Chromium, but presents a periodic screenshot stream over HTTP, not a low-latency VNC/video desktop.
- Add Watch uses the normal browser-step screenshot flow without the previously added 2-second settling / 15-second challenge waits. Known challenge screenshots can be shown without saving them as normal baselines.
- Shared scheduled watches attempt to detect known Google/Cloudflare verification pages **before** normal extraction, keep the last good content, and can notify via configured Apprise channels on first detection and later recovery. Detection and successful Telegram delivery are not guaranteed.

## Minimal deployment

```bash
cd ~/app/changedetection.io
mkdir -p datastore cloakbrowser-home browser-profile backups
chmod 700 cloakbrowser-home browser-profile backups
# Only when .env does not exist:
cp -n .env.cloakbrowser.example .env
# Set CLOAKBROWSER_LICENSE_KEY in .env without printing it in logs.
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs --tail=100 changedetection
```

Do not overwrite an existing `.env` or remove an existing Profile. Read [OPERATIONS.md](OPERATIONS.md) before backing up, restoring, or debugging startup failure.

## Important limits

One shared Context deliberately shares site state; per-watch incompatible proxy/User-Agent settings cannot be isolated. One persistent Profile must never have multiple simultaneous writers. The free CloakBrowser license was observed to permit one concurrent browser *session*, not only one Page; separate `html_cloakbrowser` launches may contend with that limit. CAPTCHA challenges still require the website to accept a human interaction; manual control is not a guarantee of passage.

### Round 2: frontend consolidation (2026-11-03)

Manual browser frontend was split into focused local JS modules and CSS. This is a maintainability / connection-state change only: underlying CloakBrowser, manual HTTP API, JPEG polling transport, watch scheduling, shared Profile and notification logic are unchanged. See [MANUAL_BROWSER.md](MANUAL_BROWSER.md) for file ownership and `node --test` checks. Real browser and Docker verification are still required on the deployment host.
