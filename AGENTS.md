# AI handoff: changedetection.io fork

This repository is a modified changedetection.io deployment. **Read this file first** when working on CloakBrowser, Docker deployment, manual browser control, notification reliability, or shared Profile behavior. This document supplements rather than overrides instructions from the original project.

## Source of truth and reading order

1. [`docs/cloakbrowser/README.md`](docs/cloakbrowser/README.md): current behavior, scope and navigation.
2. [`docs/cloakbrowser/ARCHITECTURE.md`](docs/cloakbrowser/ARCHITECTURE.md): concurrency, ownership, fetcher integration, reliability invariants.
3. [`docs/cloakbrowser/MANUAL_BROWSER.md`](docs/cloakbrowser/MANUAL_BROWSER.md): authenticated control flow and lifecycle.
4. [`docs/cloakbrowser/VERIFICATION.md`](docs/cloakbrowser/VERIFICATION.md): Google/Cloudflare detection and notification state.
5. [`docs/cloakbrowser/OPERATIONS.md`](docs/cloakbrowser/OPERATIONS.md): deployment, backup, diagnostics.
6. [`docs/cloakbrowser/UPSTREAM.md`](docs/cloakbrowser/UPSTREAM.md): pinned dependencies, upstream compatibility boundaries.
7. [`docs/cloakbrowser/CHANGELOG.md`](docs/cloakbrowser/CHANGELOG.md): historical change groups, not a substitute for code inspection.

**Implementation wins over docs** if inconsistent. Before editing existing code, read each entire affected file and its callers, then verify actual current branch/revision. The historical documents in `docs/cloakbrowser/history/` are *not* current instructions.

## Non-negotiable architecture invariants

- One Docker service, one application process and a single manager-owned CloakBrowser **persistent Context** for the `html_cloakbrowser_shared` backend. A watch check or live preview leases an individual Page/Tab; only BrowserManager may close the persistent Context.
- BrowserManager's dedicated asyncio loop owns all shared Playwright objects. Do not call their methods directly from Flask or worker threads; use the manager dispatch path.
- Page permits (`CLOAKBROWSER_MAX_PAGES`) must be released only after confirmed Page close, or known browser-generation retirement; cancellation and crash recovery must not accidentally open a second Profile writer.
- `browser-profile/` is shared intentionally; sessions, cookies and LocalStorage are *not watch-isolated*. Never start two browser processes writing the same Profile.
- The original independent `html_cloakbrowser` plugin remains installed and unmodified. The local `html_cloakbrowser_shared` adapter intercepts the upstream launch call; upgrades require compatibility review.
- Human control uses the same browser/Profile and requires authenticated changedetection.io access. Never expose unauthenticated remote browser, CDP or VNC control.
- Recognized verification pages must not become successful monitor baselines. Verification notifications are **best-effort**, stateful and separate from ordinary content-change alerts.

## Repository map

| Area | Main paths |
| --- | --- |
| Image and runtime | `Dockerfile.cloakbrowser`, `docker-compose.yml`, `requirements-cloakbrowser.txt`, `.env.cloakbrowser.example` |
| Shared backend | `integrations/cloakbrowser-shared/changedetection_cloak_shared/` |
| Watch processing and alerts | `changedetectionio/worker.py`, `changedetectionio/verification_alerts.py`, `changedetectionio/notification_service.py` |
| Visual preview and browser steps | `changedetectionio/blueprint/add_watch_ui/`, `changedetectionio/blueprint/browser_steps/` |
| Manual browser | `changedetectionio/blueprint/manual_browser/` (`manual-browser.js`, `manual-core.js`, `manual-stream.js`, `manual-input.js`, `manual-layout.js`, CSS) and `changedetection_cloak_shared/manual_session.py` |
| Tests | `tests/cloakbrowser_shared/` |

## Safe edit and verification workflow

- Keep changes limited to task-relevant files. Do not rewrite a file from a partial snippet, reconstruct an absent file, or silently replace newer fork changes with upstream/older ZIP code.
- Run Python syntax checks, relevant unittest suites and frontend syntax/template checks where applicable. Browser/Telegram/Docker end-to-end behavior must be confirmed on the operator's own deployment; do not claim it passed unless it was run.
- For source changes in the image, rebuild: `docker compose build` then `docker compose up -d --force-recreate`.
- Do **not** overwrite `.env`, delete `datastore/` or `browser-profile/`, change browser-profile permissions recursively, or copy an active Profile. Use the documented offline backup process.
- Never commit or include in an AI ZIP: `.env`, license keys, `datastore/`, `browser-profile/`, `cloakbrowser-home/`, `backups/`, cookies, auth tokens or private logs.
- When handing off incremental changes to this user, deliver one ZIP with complete new/modified files at their repository-relative paths below `payload/`. For deletions/renames, include `__delete__.txt` at ZIP root. No backup ZIP is needed.
- Update the current relevant documentation and `CHANGELOG.md` whenever behavior changes; avoid adding a new round-specific document for every patch.

## Current vs planned

Current human control is a real Chromium/Playwright Page, displayed through periodic JPEG HTTP screenshots and controlled by HTTP mouse/keyboard actions. **It is not a native streamed desktop.** CDP screencast or Xvfb/noVNC are options under discussion, **not installed or enabled**. Do not describe them as present functionality.

## Manual frontend development

The manual browser uses plain JS scripts in dependency order: `manual-core.js` -> `manual-stream.js` -> `manual-layout.js` -> `manual-input.js` -> `manual-browser.js`. Do not introduce an unrelated frontend bundler, a second browser process, or unauthenticated control endpoints for simple UI work. Preserve request-order guarantees and the session token/epoch checks when adding new UI features. Validate with `node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs` plus actual Playwright/CloakBrowser acceptance tests on the user's Docker host.
