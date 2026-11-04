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

## Product extraction rules (new)

`extractor-rules/` is **Git tracked** and bind-mounted writable as `/extractor-rules`. It contains no secrets or user sessions. The `changedetectionio/product_extraction/` engine uses only declarative JSON rules. The `/product-extractors/` WebUI is authenticated; dry-run must not update Watch history, notification state or checksums. Stock and price alerts are implemented in `processors/restock_diff/purchase_alert.py` and integrated by `processor.py`; consult `docs/product-extraction/STOCK_PRICE_RULES.md` for current monitoring rules. Never convert unmatched/unknown stock into an out-of-stock or in-stock assertion. Rule changes require a new extraction baseline, not a false price alert.

## Asking another AI to author product rules

Start with `extractor-rules/AI_RULE_GUIDE.md` (self-contained rule-writing instructions). The schema is `extractor-rules/schema/product-rule.schema.json`; the offline HTML/JSON pair in `extractor-rules/examples/sample-product.*` demonstrates tested selector behavior. Rules generated for real websites require real DOM evidence and Dry Run testing, not screenshot-based guessed selectors. Keep rules in the Git-tracked `extractor-rules/rules/` tree; WebUI saves do not create Git commits.

## Browsers UI styling

The manual browser template and `manual-browser.css` use the compact Product Extractors visual language but prioritize the full-height interactive screenshot. Do not inflate header or toolbar height, break the existing `manual-*` element IDs, or change the five JS modules' dependency order when making visual-only improvements. Keep the text-input toolbar always visible above the browser canvas; technical details may remain collapsible.


Product Extractors V2: consult `extractor-rules/AI_RULE_GUIDE.md` before preparing JSON rules. Validate multiple product and stock cases; never assume a single successful Dry Run validates a whole retailer. Manual Browsers supports fixed/follow-window viewport modes.

## Product rules lifecycle and viewport defaults (2026-11)

The Product Extractors UI now supports duplicate/delete, revision-protected overwrite, and explicit linked-Watch checks before deletion. `id` is the Git-tracked filename, not a random UUID. Do not bypass the `registry.py` `WRITE_LOCK`, current-revision checks, or the authenticated `/product-extractors/api/` routes. Shared dropdown behavior is in `changedetectionio/static/js/custom-select.js` and `changedetectionio/static/css/custom-select.css`; existing native select values/events remain authoritative.

`CLOAKBROWSER_VIEWPORT_WIDTH` (default `1366`) and `CLOAKBROWSER_VIEWPORT_HEIGHT` (default `900`) define scheduled shared-Watch, online Dry Run, and manual fixed-viewport size. `changedetectionio/product_extraction/viewport.py` is the common parsing/validation code. Manual follow-window mode remains a per-Page exception; fixed mode uses screenshot aspect ratio rather than stretching to full page height. Changing env vars requires container recreation.

## Current Stock & Price policy (2026-11)

Read [`docs/product-extraction/STOCK_PRICE_RULES.md`](docs/product-extraction/STOCK_PRICE_RULES.md), the exact Markdown source embedded in the Watch/Tag help panel, and [`docs/product-extraction/RESTOCK_AND_ALERTS.md`](docs/product-extraction/RESTOCK_AND_ALERTS.md) before changing product stock or price notifications. The WebUI is price-first; stock current-state filters require an enabled price rule; stock events combine with price using AND (default) or OR. Fixed-price continued-change alerts default to enabled, and percentage comparisons use a separate persistent anchor. Existing `purchase_alert_state` is separate from display-oriented `restock` and is not reset by unknown input. Old `alert_mode` / `target_price` configurations are **not migrated** in this development-phase change. Do not change the Worker/Apprise first-check gate without a separate requirement.
