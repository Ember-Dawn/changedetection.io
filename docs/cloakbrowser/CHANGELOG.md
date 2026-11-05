# CloakBrowser fork change history

This is a **feature and patch history**, reconstructed from the maintained source and prior delivery artifacts. It is **not** a release-tag list and does not imply that each step has a verified Git commit. For the current architecture use README, ARCHITECTURE, MANUAL_BROWSER, VERIFICATION and OPERATIONS instead. More detailed older incident notes are archived in [`history/`](history/).

| Sequence | Implemented change and affected areas | Notes / testing evidence |
| --- | --- | --- |
| 1. Single-container runtime | `Dockerfile.cloakbrowser`, `docker-compose.yml`, requirements and env template; bind mounts for datastore, browser binary/cache, Profile | Self-built Docker image; actual license/download is runtime dependent |
| 2. Shared persistent Context | `integrations/cloakbrowser-shared/`, shared fetcher registration, Browser Steps and Add Watch routing, WorkerPool cancellation | Local plugin beside untouched upstream isolated backend |
| 3. Reliability and Profile handling | Manager generation/recovery state, Page lease/quota, shutdown tracking, on-disk lock and offline backup/restore CLI | Defensive fail-closed behavior; Profile cannot have two writers |
| 4. Screenshot fix | `changedetectionio/content_fetchers/playwright.py` handles `page.viewport_size=None` for persistent contexts | Incident: real WebUI preview returned HTTP 502 due to `NoneType` viewport indexing; see archived viewport note |
| 5. Page readiness | Shared-browser Google/Cloudflare checks, initial optional wait and baseline protection | Subsequent patch **removed extra waits** from current Add Watch/monitoring behavior; archived note is historical |
| 6. Human-operated browser | Authenticated manual session manager and `/manual-browser/` UI, JPEG frame polling, Playwright input, watch reservation, resume/switch, URL navigation | Same Profile/Context; manual session uses a Page permit, not separate browser |
| 7. User experience | Manual buttons named **人工操作**, sidebar **Browsers** entry, compact navigation, URL sync, frame/status retry, full remaining-height view and Page viewport mapping | At that historical milestone the view was HTTP screenshot polling; V2 later added WS JPEG and V5 added experimental CDP (still not noVNC) |
| 8. Verification alert protection | Early challenge detection before shared XPath extraction, filter-failure fallback, Google/Cloudflare classification, deduplicated Apprise/Telegram queue alerts and recovery handling | Alert *queued* vs *delivered* is distinct; only operator can validate real Telegram delivery |
| 9. Documentation consolidation | New root `AGENTS.md`, topic-centered authoritative docs, archived incident notes | **Documentation-only**; no browser/runtime behavior changes in this round |
| 10. 2026-11-03 backend reliability/refactor round 1 | `manual_session.py`, `manager.py`, `page_readiness.py`, `verification_alerts.py`, notification queue consumer and Worker, targeted tests and docs | Single expiry supervisor survives token rotation; notification delivery acknowledgements with cooldown and pending expiry, stale-event rejection, recovery after final history persistence; retired unused preview wait helper. No UI or Docker changes. Synthetic tests only; real Chromium/Telegram acceptance required. |

| 11. 2026-11-03 frontend refactor round 2 | Manual `manual-core.js`, `manual-stream.js`, `manual-input.js`, `manual-layout.js`, simplified `manual-browser.js`, extracted `manual-browser.css`, template loader, mock-based Node tests and current docs | Reuses the same backend HTTP endpoints and BrowserManager, improves stale response and pointer-capture recovery, keeps screenshot polling. Node simulated tests only; real Chromium/Docker and existing watch behavior require local acceptance. |

## Updating this log

For future source changes, append a new entry with date (if known), specific paths, user-visible behavior, compatibility risks and *actual* validation performed. For uncertain claims, say “not verified” rather than marking a test passed. Only authoritative current documents should describe the desired production behavior; incident reports under history are snapshots in time.

## 2026-11-03: published host port binding

- `docker-compose.yml`: publish `${CHANGEDETECTION_PORT:-9901}:5000` instead of binding only to `127.0.0.1`. This permits LAN/network access subject to firewall and routing.
- `docs/cloakbrowser/README.md` and `OPERATIONS.md`: update host exposure and security guidance.
- No browser/session logic changed. Docker runtime and firewall behavior were not tested in this authoring environment.

## 2026-11: Git-managed product extraction rules (first phase)

- Added `/product-extractors/` WebUI to import/edit declarative JSON rules and run read-only extraction tests.
- Rules reside in Git-tracked `extractor-rules/rules/*.json` and are mounted into Docker, not baked into the image.
- Restock watches now choose `auto`, `rule` or `builtin`; custom rule output wins over generic metadata.
- Rule SHA-256 participates in restock reprocessing; changes to rules do not themselves trigger a price-change notification.
- Fixed Watch notification test display and aligned inherited test URLs with normal notification fallback.
- No previous watch data migrations are supplied; this repository is in development with test data.

## Product Extractors UI refinement

- Use the supported Feather `package` icon in both desktop and mobile navigation.
- Split Product Extractors UI into a Jinja template, scoped CSS, and vanilla JavaScript; no new runtime dependencies or backend API changes.
- Group rule management, JSON editing, dry run, and results in separate responsive panels.
- Add consistent controls, accessible import trigger, unsaved-change confirmation, busy/error states, result copy, and inline validation feedback.
- Preserve existing rule save/list/test endpoints and original control IDs.

## 2026-11-03: Product rule authoring guide and Browsers visual refinement

- Added `extractor-rules/AI_RULE_GUIDE.md`: standalone instructions for another AI to generate schema-v1 JSON rules from real rendered HTML/DOM, including limits of the implementation, price and stock disambiguation, expected response format and Dry Run procedure.
- Added a non-sensitive, offline-testable demonstration pair in `extractor-rules/examples/sample-product.html` and `sample-product-rule.json`. Real retailer selectors are intentionally **not** fabricated.
- Updated `extractor-rules/README.md` and `AGENTS.md` with navigation to the guide.
- Restyled Browsers into a compact workspace aligned with Product Extractors. It preserves viewport fill, existing control IDs and the current five-module JavaScript interaction engine. Additional controls are collapsible to maximize the browser frame.
- Added checks for template contract, selector example and guide links. No new browser protocol, container, backend API or JS build tool.

## 2026-11-03: Browsers typing toolbar, session detail and interaction responsiveness

- Move text input above the remote browser viewport, keep it single-row and always visible; limit input width without shrinking the remaining-height viewport unnecessarily.
- Replace the concatenated technical status with a collapsible grid and per-line URL/usage notes; move per-site Cookie/LocalStorage counts into details.
- Prompt a coalesced screenshot after remote input succeeds, use adaptive JPEG frame intervals, and expose request/frame diagnostics; retain HTTP JPEG transport and single-flight/stale-session safeguards.
- Add mock-based interaction/stream tests and template UI assertions. No server-side browser lifecycle, Profile, Watch history, or notification API changes. Real Docker/Chromium latency measurements remain to be verified.


## Product Extractors V2 and manual viewport modes (2026-11-03)

- Added bounded tri-state JSON rules for Pickup, Shipping and composite availability; no arbitrary scripting.
- Added extraction summary, per-field diagnostics, optional same-Page Dry Run screenshot and compact editor styling.
- Added manual viewport fixed/follow-window preference and explicit 1366×768 for shared Watch pages.
- Added documented synthetic multi-product scenarios; real-world Micro Center screenshots must still be checked in Docker.

## 2026-11-03: rule management and fixed viewport refinement

- Product Extractors: add rule copy, reference-checked deletion, duplicate-ID confirmation, optimistic revision checks for updates/deletion, and copy actions next to the field diagnostics. Keep rules under Git-tracked `extractor-rules/rules/`.
- Browsers and Product Extractors: use a shared accessible dropdown enhancement rather than raw native popup styling; native controls remain data sources and no UI library is introduced.
- Define shared desktop viewport from Compose env (1366×900 default), used by scheduled shared Watch, Product Extractors live Dry Run and manual fixed mode. Fixed mode now sizes the screenshot container to its aspect ratio; follow-window still grows with the WebUI.
- Add standalone registry lifecycle tests. Docker/real Chromium/manual-pixel testing must still be performed on deployment.

### 2026-11 — Purchase-condition notification policy and Watch editor

- Replace the legacy `restock_diff` mixed stock/price percentage filtering with three explicit purchase goals: stock-only, price-only, stock-and-price. A qualified price change **up or down** triggers; unchanged prices do not.
- Preserve initial-check baseline behavior and existing Worker/Apprise notification gating. No first-check notifications. Unknown extraction data does not reset reliable qualification. Mode/target edits or extraction-rule revisions start a fresh baseline.
- Save `purchase_alert_state` on Watch, update processor API schema and tests. Improve Watch editor radio alignment, show `name — id` with shared custom select, remove redundant top manual-operation button.
- Add `docs/product-extraction/RESTOCK_AND_ALERTS.md` as the notification semantics source of truth.

## 2026-11-05: Manual Browser Socket.IO input / binary JPEG streaming

- `manual_socket.py` registers protected input and frame namespaces; connects require active password login, CSRF, session owner and browser generation; JPEG delivery uses explicit frame acknowledgement.
- `manual-transport.js` adds independent Socket.IO connections, ordered operation ACK and safe HTTP fallback, keeping the shared Headless BrowserManager and Profile unchanged.
- Existing manual frontend gains real Hover, final-move-before-release, and a compact transport diagnostic.
- Screenshot encoder stays JPEG 65; CDP Screencast, WebP, Xvfb and noVNC remain unimplemented.
- Tests: frontend Node tests and source/template checks are run locally. No real Chromium, production Cloudflare or Docker acceptance is claimed.

## 2026-11-05: Browsers diagnostics, themed transport control and UA

- Split manual frame timing into Playwright screenshot duration versus BrowserManager dispatch/return overhead. Expose JPEG size and the previous Socket.IO send-to-consumption acknowledgement time for diagnosis, without claiming exact one-way transport timing.
- Change FPS display from a noisy single-frame interval to a five-second displayed-frame observation with stale-frame zeroing; retain adaptive 10/5/2 FPS caps and one-frame backpressure.
- Reuse existing CDSelect for transport preference instead of the native-looking dropdown; preserve localStorage preference and HTTP fallback.
- Add current Page UA, Platform, Viewport and DPR plus a copy control in the collapsed session detail; the Page is still Headless. Display only non-secret browser metadata.
- New tests cover status rendering, stream metrics and template/metadata contracts. Real Docker/Chromium FPS remains to be measured on the operator host.

## 2026-11-05: Browsers session detail UI V4

- Condense the diagnostics view to three primary performance metrics with optional detailed timings and collapsible usage instructions; keep all existing counters and transport controls.
- Show only the live User-Agent in the browser environment section, with its existing copy action; remove redundant Platform/Viewport/DPR rows.
- Add a copyable current URL, a theme-matched thin details scrollbar and responsive compact layouts. No browser, Socket.IO, Profile or monitoring behavior changes.


## 2026-11-05: Experimental CDP Screencast option

- Added `changedetection_cloak_shared/manual_screencast.py` to create and dispose a CDPSession for the same manual Page, receive `Page.screencastFrame`, acknowledge CDP frame IDs, and retain only the most recent pending JPEG.
- The `/manual-frames` Socket.IO producer may use CDP as a frame source, with an initial-frame timeout and fallback to ordinary WebSocket JPEG screenshots. The established HTTP path, mouse/keyboard handling, single browser/Profile and 15-minute session lifetime remain unchanged.
- The themed manual detail dropdown offers **CDP Screencast（实验性）** without making it the default; mode changes restart only the frame transport. Incoming frames identify their source and CDP capture-duration fields are not fabricated.
- Validation in authoring environment: Node frontend tests, manual workspace contract tests, CDP fake-session lifecycle tests and syntax checks. Real CloakBrowser/Chromium and actual FPS **not tested**; this is an opt-in experimental feature.

## 2026-11-05: Documentation status reconciliation

- Added [STATUS.md](STATUS.md) to separate implemented V2–V6 features from experimental CDP and still-outstanding real-host acceptance.
- Reconciled current manual transport/UI descriptions that still referred to HTTP-only polling, a duplicate URL field, or the former position of frame controls. Historical milestone descriptions remain historical.
- Corrected the CloakBrowser README product-policy note: the 2026-11-04 source review found expanded fields aligned, while legacy stored data and true end-to-end behavior still need validation. No application runtime code was changed in this documentation pass.

## 2026-11-05: Browsers UI refinement V6

- Move **关闭会话** to the right of **连接浏览器** and use a clearly red danger style. Restrict **完成并重新检查** to sessions whose actual Watch UUID matches the Watch-specific page entry; add server-side validation before closing on `/api/finish`. Generic Browsers visits and generic session resumes do not display the action.
- Move CDP/WS JPEG engine selection and WebSocket/HTTP preference next to viewport mode; keep themed select components and visible connection/engine status. Remove redundant interactive-view status copy, duplicate detailed URL display and URL copy action; keep the address bar authoritative.
- Clarify operation response and CDP diagnostics, retain lower collapsible metrics, UA and help. No redesign of responsive toolbars or collapse of text entry. Existing Headless shared Profile, CDP, HTTP and WebSocket internals remain unchanged.
- Verification: JavaScript mocked front-end checks, template contracts and source syntax; real Docker/Chromium visual behavior not proven in the authoring environment.
