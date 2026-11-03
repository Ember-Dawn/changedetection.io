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
| 7. User experience | Manual buttons named **人工操作**, sidebar **Browsers** entry, compact navigation, URL sync, frame/status retry, full remaining-height view and Page viewport mapping | Current remote view remains screenshot polling; not noVNC/CDP streaming |
| 8. Verification alert protection | Early challenge detection before shared XPath extraction, filter-failure fallback, Google/Cloudflare classification, deduplicated Apprise/Telegram queue alerts and recovery handling | Alert *queued* vs *delivered* is distinct; only operator can validate real Telegram delivery |
| 9. Documentation consolidation | New root `AGENTS.md`, topic-centered authoritative docs, archived incident notes | **Documentation-only**; no browser/runtime behavior changes in this round |

## Updating this log

For future source changes, append a new entry with date (if known), specific paths, user-visible behavior, compatibility risks and *actual* validation performed. For uncertain claims, say “not verified” rather than marking a test passed. Only authoritative current documents should describe the desired production behavior; incident reports under history are snapshots in time.
