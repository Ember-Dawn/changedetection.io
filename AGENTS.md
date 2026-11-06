# AI handoff: changedetection.io fork

This repository is a modified changedetection.io deployment. **Read this file first** when working on CloakBrowser, Docker deployment, manual browser control, notification reliability, or shared Profile behavior. This document supplements rather than overrides instructions from the original project.

## Source of truth and reading order

1. [`docs/cloakbrowser/README.md`](docs/cloakbrowser/README.md): current behavior, scope and navigation.
   [`docs/cloakbrowser/STATUS.md`](docs/cloakbrowser/STATUS.md): current progress, evidence and remaining validation.
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

Browsers has two mutually exclusive human-control modes. **截图操控** uses a Headless Playwright Page with Socket.IO JPEG frames, ordered input and HTTP fallback; optional CDP Screencast is still experimental. **实时浏览器** temporarily pauses Watch admission, closes Headless and runs the same persistent Profile in Headed Chromium on Xvfb, controlled through authenticated noVNC/WebSocket; exiting restores Headless and Watch admission. The user has confirmed the integrated noVNC display and the V8 bottom-black-strip correction on Docker, not full crash/rollback acceptance or particular websites' login persistence. Never open two Profile writers, expose unauthenticated VNC ports or bypass the maintenance gate. See `docs/cloakbrowser/STATUS.md`.

## Manual frontend development

The manual browser uses plain JS scripts in dependency order: `manual-core.js` -> `manual-transport.js` -> `manual-stream.js` -> `manual-layout.js` -> `manual-input.js` -> `manual-browser.js`. Do not introduce an unrelated frontend bundler, a second browser process, or unauthenticated control endpoints for simple UI work. Preserve request-order guarantees and the session token/epoch checks when adding new UI features. Validate with `node --test tests/cloakbrowser_shared/test_manual_browser_frontend.cjs` plus actual Playwright/CloakBrowser acceptance tests on the user's Docker host.

## Product extraction rules (new)

`extractor-rules/` is **Git tracked** and bind-mounted writable as `/extractor-rules`. It contains no secrets or user sessions. The `changedetectionio/product_extraction/` engine uses only declarative JSON rules. The `/product-extractors/` WebUI is authenticated; dry-run must not update Watch history, notification state or checksums. Stock and price alerts are implemented in `processors/restock_diff/purchase_alert.py` and integrated by `processor.py`; consult `docs/product-extraction/STOCK_PRICE_RULES.md` for current monitoring rules. Never convert unmatched/unknown stock into an out-of-stock or in-stock assertion. Rule changes require a new extraction baseline, not a false price alert.

Product rule `fields.currency` may either use the existing selector form or `{"literal":"USD"}` with a recognized uppercase ISO 4217 code; the two forms are mutually exclusive and there is no fallback. Other fields are unchanged. `condition.op=literal` for stock is unrelated. Ensure validator, JSON Schema, evaluator and `AI_RULE_GUIDE.md` remain consistent. Changing a currency rule affects its extraction signature and may reset alert baseline on the next check, without deleting Watch history.

## Asking another AI to author product rules

Start with `extractor-rules/AI_RULE_GUIDE.md` (self-contained rule-writing instructions). The schema is `extractor-rules/schema/product-rule.schema.json`; the offline HTML/JSON pair in `extractor-rules/examples/sample-product.*` demonstrates tested selector behavior. Rules generated for real websites require real DOM evidence and Dry Run testing, not screenshot-based guessed selectors. Keep rules in the Git-tracked `extractor-rules/rules/` tree; WebUI saves do not create Git commits.

## Browsers UI styling

The manual browser template and `manual-browser.css` use the compact Product Extractors visual language but prioritize the full-height interactive screenshot. Do not inflate header or toolbar height, break the existing `manual-*` element IDs, or change the six JS modules' dependency order when making visual-only improvements. Keep the text-input toolbar always visible above the browser canvas; technical details may remain collapsible.


Product Extractors V2: consult `extractor-rules/AI_RULE_GUIDE.md` before preparing JSON rules. Validate multiple product and stock cases; never assume a single successful Dry Run validates a whole retailer. Manual Browsers supports fixed/follow-window viewport modes.

## Product rules lifecycle and viewport defaults (2026-11)

The Product Extractors UI now supports duplicate/delete, revision-protected overwrite, and explicit linked-Watch checks before deletion. Editing the currently loaded rule saves without extra confirmation; conflicting new/imported/renamed IDs use an accessible custom confirmation dialog with Enter/Escape, as do discard/delete operations. Preserve server-side revision checks. `id` is the Git-tracked filename, not a random UUID. Do not bypass the `registry.py` `WRITE_LOCK`, current-revision checks, or the authenticated `/product-extractors/api/` routes. Shared dropdown behavior is in `changedetectionio/static/js/custom-select.js` and `changedetectionio/static/css/custom-select.css`; existing native select values/events remain authoritative.

`CLOAKBROWSER_VIEWPORT_WIDTH` (default `1366`) and `CLOAKBROWSER_VIEWPORT_HEIGHT` (default `900`) define scheduled shared-Watch, online Dry Run, and manual fixed-viewport size. `changedetectionio/product_extraction/viewport.py` is the common parsing/validation code. Manual follow-window mode remains a per-Page exception; fixed mode uses screenshot aspect ratio rather than stretching to full page height. Changing env vars requires container recreation.

## Current Stock & Price policy (2026-11)

Read [`docs/product-extraction/STOCK_PRICE_RULES.md`](docs/product-extraction/STOCK_PRICE_RULES.md), the exact Markdown source embedded in the Watch/Tag help panel, and [`docs/product-extraction/RESTOCK_AND_ALERTS.md`](docs/product-extraction/RESTOCK_AND_ALERTS.md) before changing product stock or price notifications. The WebUI is price-first; stock current-state filters require an enabled price rule; stock events combine with price using AND (default) or OR. Fixed-price continued-change alerts default to enabled, and percentage comparisons use a separate persistent anchor. Existing `purchase_alert_state` is separate from display-oriented `restock` and is not reset by unknown input. Old `alert_mode` / `target_price` configurations are **not migrated** in this development-phase change. Do not change the Worker/Apprise first-check gate without a separate requirement.

## Notification templates (2026-11)

**First read [`docs/product-extraction/NOTIFICATION_TEMPLATES.md`](docs/product-extraction/NOTIFICATION_TEMPLATES.md).** `notification/templates.py` currently has **six** built-ins and up to 50 Unicode-named custom templates stored under `settings.application.notification_templates`. The library stores name/title/body/format, never notification URLs, and does not automatically overwrite Watch/Tag/Global settings. Selecting a template changes Format immediately; Title/Body change only on **Apply to editor**; normal Save is separate. Guard unapplied format/body mixtures. Newly created or converted `restock_diff` Watches get `builtin-product-html-compact` copied only when their notification fields are uncustomized and every effective Watch→Tag→Global destination is `tgram://`; empty, mixed, or non-Telegram destinations retain defaults. Existing Watches must not be auto-migrated. The UI may show an exact Title/Body/Format match without persisting a template ID. Use accessible custom dialogs, not browser `prompt`/`confirm`, for name/create/update/delete; Enter confirms except IME composition, Esc cancels.

Product presentation comes from `processors/restock_diff/__init__.py` tokens, not new policy decisions inside Jinja2. Price-only hides stock, stock-only hides price; percentage changes share one comparison anchor, and test messages must not imply real price or stock triggering. Keep preview read-only and text-safe. Preserve generic defaults, Watch→Tag→Global inheritance, and the existing Apprise queue. Keep Rich JSON in the original plain textarea.

Notification Preview is a read-only Jinja2 preview with collapsible Rendered/Raw tabs. Rendered uses allowlisted DOM nodes for HTML and conservative format-specific Markdown/Telegram/Rich presentation; Raw displays rendered source, not the final Apprise wire payload. Never put untrusted Watch content into `innerHTML`, and never let Preview send or commit anything. Keep stale-result and concurrent-request protection; Telegram appearance is approximate.

## Telegram notification formats (2026-11)

The Notification template library saves the message format with each template. Applying a preset copies title, body, and format to the existing fields; it does not save the Watch by itself. Telegram-specific formats are `telegram_html`, `telegram_markdownv2`, and `telegram_rich`; they require `tgram://` destinations. Rich JSON messages are validated and written to mode-0600 temporary files used by Apprise's `template` URL option, then removed in a `finally` block. Do not expose arbitrary server file paths or send JSON blocks as a regular HTML/text notification. Product presets use conditional price/stock rows. Plain Text shows inline details and URL. HTML includes a linked title and offers compact and all-details options; its internal title renders empty to avoid duplication. Rich uses a linked size-5 Watch heading without cart icon or separate View product row, and a native `details` block. Confirm actual Apprise and mobile Telegram compatibility before describing Rich support as production-verified.

Telegram Rich UI: `telegram_rich` hides only the visible Notification Title
form group; do not disable or clear the underlying input, which still belongs
to saved template data and is required for normal formats. The Rich heading
is inside the one-line Body JSON; the built-in product preset uses the Watch
title and a typed RichText `url` object for the short product link.

## Product purchase-policy integration status (reviewed 2026-11-04)

The current `processors/restock_diff/forms.py`, `processor.py` and `api.yaml` use the expanded `price_mode` / `stock_mode` / `price_threshold` contract from `purchase_alert.py`; previous notes claiming those files still rely on `alert_mode` / `target_price` were out of date. Validate the integrated form, API and evaluator in tests when modifying their behavior. Old configurations are not automatically migrated. Offline fixture tests do not prove end-to-end browser or Telegram delivery.

## Product rule page waits and operational failures (2026-11)

- JSON Schema v1 accepts optional `page.extra_wait_seconds` (integer 0–30), with the registry validator and JSON Schema kept in sync. Watch-level explicit wait including 0 overrides rule-level extra wait.
- The Watch stock/price editor suggests a unique URL-matching selected rule without silently changing existing bindings. Auto is removed from new UI choices; legacy stored auto is still understood.
- The extraction-only signature (rule ID + fields) avoids resetting price/stock baselines for waits, names or URL patterns. Handle older stored signatures without forced reset.
- Product rule failures use a separate persisted and delivery-acknowledged failure/recovery notifier. Never interpret unavailable price/stock as zero or out-of-stock. Do not change existing commodity notification templates to implement operational notices.

### Product Extractors save and revision contract (2026-11-05)

- The server-rendered Current rule dropdown is not the source of truth for client-side rule revisions. On page initialization, `product-extractors.js` must load `/product-extractors/api/list` and populate both `rulesIndex` and `revisions` before permitting saves. Failure to load the list must fail closed.
- Editing the currently loaded rule ID updates it with `overwrite: true` **and** the stored `expected_signature`; imported/new JSON with an existing ID requires the custom confirmation dialog. Do not bypass the registry's atomic revision guard.
- API save uses `RULE_ID_CONFLICT` and `RULE_REVISION_CONFLICT` codes alongside HTTP 409. An ID conflict can be explicitly confirmed after refreshing revisions; a stale revision must require reload, never be silently overwritten.
- The product rule dialog accepts Enter to confirm and Escape to cancel. Keep script asset cache-busting when changing editor behavior; run the behavioral Node test as well as Python contracts.

## Manual Browser diagnostics (2026-11-05)

The collapsed Browsers details panel now distinguishes BrowserManager dispatch time, in-loop Playwright JPEG screenshot time, client image-display time and the previous send-to-ack interval. FPS uses a five-second displayed-frame window and may intentionally be ~2 FPS at idle. The transport preference reuses CDSelect, and the displayed UA reflects the current manual Page (Platform/Viewport/DPR remain available internally but are hidden from the UI), not necessarily outgoing HTTP headers. Retain HTTP fallback and the one-frame WebSocket backpressure when changing this feature.

## Browsers V6 UI and Watch-context safety (2026-11-05)

- Browsers is also a general-purpose manual browsing entry. Do not show **完成并重新检查** for a sidebar/general entry or for a resumed Watch session from that entry. Show it only when the entry Watch UUID matches the session's server-derived Watch UUID, and reject `/api/finish` for a general/unowned/nonmatching token before releasing the Page. The close action remains independent.
- Navigation toolbar: Watch-only finish, **连接浏览器**, red **关闭会话**. Upper action toolbar: viewport, frame engine and transport preference via existing `data-custom-select`; the lower details section is diagnostic, not a place for repeated editing controls or URL copy. Top navigation URL is authoritative and must not be replaced during active editing. Preserve keyboard text bar and current responsive behavior; do not add a second select library.

## Live Browser V1 handoff (2026-11-05)

Current source includes integrated Headed desktop control. The operator confirmed working in-app noVNC after the `websocket=True` handshake fix and that the V8 X11 window-fit eliminated the bottom black strip; independent Headed↔Headless Cookie/LocalStorage persistence and manual VNC input/reconnect were also tested on Docker. Error recovery, simultaneous Watch drain and HTTPS reverse-proxy WSS remain acceptance items. Keep BrowserManager as sole Profile writer, do not call its shutdown `stop()` to toggle mode, never publish VNC ports, and retain maintenance pause on uncertain restore. See STATUS.md, ARCHITECTURE.md and OPERATIONS.md.


## Browsers V7 mode navigation (2026-11-05)

The separate bordered Live Browser card has been replaced with **截图操控 / 实时浏览器** view tabs in a common toolbar. Tab selection must never launch/stop Chromium; explicit start/restore buttons control the protected lifecycle. Disable capture selection whenever Headed is running or transitioning. Embedded noVNC uses the Xvfb 1366×900 aspect ratio instead of a fixed viewport-relative height, with no outer Live Browser component border. Preserve the V1 WebSocket upgrade fix, app-styled confirmation, full Profile ownership and Watch maintenance pause.

## Watch Health and product fetch reliability (2026-11)

Read [`docs/watch-health/ARCHITECTURE.md`](docs/watch-health/ARCHITECTURE.md) before modifying
product fetch retries, check scheduling, operational alerts or successful recovery.
One completed Watch check, not one tab attempt, is the health accounting unit. Keep
`Fetch Reliability` separate from `Watch Health` and from existing price/stock
business notifications. Only use the manager-owned CloakBrowser page lease and its
scoped rule-readiness hook; manual browser sessions must never inherit automatic
retry controls. Do not reinstate unconditional `clear_after_success` or product
recovery calls in Worker cleanup. Accelerated recheck configuration is stored in
`settings.requests`, with Watch-level optional overrides and persisted retry times.

## Site-paced shared-browser navigation

Global Settings > Fetching has `site_interval_seconds` (default 3) and multiline
`site_interval_overrides` (`microcenter.com = 10`, etc.). Site grouping uses an
offline PSL via tldextract. Only monitored shared-CloakBrowser main-page
`_ManagedPage.goto` calls are paced, including fresh-Tab retries; same-Tab DOM
parsing and manual browser actions are unaffected. Do not introduce a global
lock, shared-site concurrency restriction, or startup stagger. The short per-site
async lock in `changedetection_cloak_shared/site_rate_limit.py` reserves each
navigation start time; independent sites can navigate in parallel.
Watch-list Manual operation links opt into autoconnect; normal Browsers links
do not. Keep the existing active-session ownership and maintenance gate.
`FETCH_WORKERS` in Compose is environment-configurable and is not a browser count.
