# Verification interstitial handling and alerts

## Scope

This fork recognizes some Google Scholar / Google unusual-traffic pages and Cloudflare verification interstitials when using the **shared** CloakBrowser backend. Recognition is heuristic, not an anti-bot bypass. Unknown challenges and login pages may not be detected; normal content mentioning Cloudflare must not automatically become a false positive.

## Paths and behavior

| Stage | Intended current behavior | Code |
| --- | --- | --- |
| Add a Page Watch snapshot | Return screenshot promptly using existing navigation/browser-step mechanics; no extra 2 s settle or 15 s challenge wait. Show recognized challenge screenshot with a warning, but do not save it as successful temporary baseline. | `blueprint/add_watch_ui/__init__.py`, `static/add-watch.js` |
| Scheduled shared fetch | After normal upstream/per-watch delay and **before** XPath/HTML extraction, check visible page text/title/URL for known Google/Cloudflare challenges and raise a failed fetch. | `changedetection_cloak_shared/manager.py`, `page_readiness.py` |
| Failed-filter fallback | Where appropriate, inspect already obtained fetcher content if normal filter detection fails; prefer a recognized verification reason over a misleading plain filter-not-found error. | `worker.py`, `verification_alerts.py` |
| Verification status | Keep `manual_attention_reason` for recognized Google/Cloudflare challenge; preserve previous normal snapshots/change history; do not permanently set `paused`. Scheduler continues unless user has paused the watch. | `verification_alerts.py`, `worker.py` |
| Notification | Queue first actionable verification alert via existing watch/tag/global Apprise settings, including Telegram when configured. Repeat identical verified conditions should not queue repeated alerts. A genuinely successful later fetch can queue a recovery alert. | `verification_alerts.py`, `notification_service.py` |
| Manual resolution | Open the authenticated **人工操作** Page for the affected watch, interact in shared Profile, close and recheck. | `blueprint/manual_browser/`, `manual_session.py` |

The former `CLOAKBROWSER_PAGE_SETTLE_SECONDS` and `CLOAKBROWSER_CHALLENGE_WAIT_SECONDS` are retired from the *active* Add Watch and shared scheduled-fetch paths. Do not restore these waits casually. Upstream `WEBDRIVER_DELAY_BEFORE_CONTENT_READY` and watch-specific **Wait seconds before extracting text** remain in effect.

## Notification state: detection is not delivery

`verification_alerts.py` separates three states:

- `manual_attention_reason`: currently identified Google/Cloudflare verification, independent of watch pause state.
- `manual_attention_pending_token` / `manual_attention_pending_since`: one in-flight attention alert, matching the notification queue item. Pending entries expire after 10 minutes so a process restart cannot leave a watch permanently stuck.
- `manual_attention_notified_reason`: set **after Apprise actually returns success**, not merely after queue admission.

Failures clear the pending token and may retry on a later scheduled check with a **5-minute minimum cooldown**. The existing notification worker handles Apprise delivery and records the result through `acknowledge_delivery()`. A missing notification URL does not start the retry cooldown. An obsolete queued alert is skipped if the watch has already recovered or the token changed.

When a normal fetch and processing finish, the watch state is cleared and a recovery message is queued only if the original attention alert was confirmed successful. Recovery notices also use matching tokens and an independent retry state (`manual_attention_recovery_*`). A newer verification invalidates a pending recovery. A recovery is considered successful only after the Worker has saved history and final metadata; an unchanged checksum is already a successfully fetched no-op.

**Limitations:** a notification that reached Telegram but whose acknowledgement was lost may be retried. The app cannot provide transactional exactly-once delivery across process crashes and an external transport. Actual delivery remains dependent on correct credentials and network access. Monitor the notification debug log if messages do not arrive.

Watch state is not a user pause. Scheduler retries at its configured cadence; for challenge-prone websites prefer a sensible interval rather than aggressive rechecking. Preserve last successful content while the challenge remains.

## Test matrix for maintainers

1. Ordinary Google Scholar page (no false alarm) and Chinese-language Scholar verification page (first alert).
2. Ordinary Micro Center product page and Cloudflare `Performing security verification` page (first alert).
3. Repeated same challenge: no additional alert.
4. Challenge with no notification URL configured: status recorded; once configured, a later check may enqueue it.
5. Recovery: a truly successful check clears the state and queues one recovery notice only if the initial alert was acknowledged as successfully delivered.
6. A failed Telegram delivery, stale queued notification, or interrupted container restart: retry without permanent suppression or uncontrolled spam.
7. An unknown challenge page: normal error handling, no fabricated verification alert.
8. Add Watch preview must show screenshot without challenge-specific extra waiting and must not save challenge content as a baseline.
9. Use a real Telegram test endpoint only with operator approval; mock tests cannot prove message delivery.

The original independent `html_cloakbrowser` backend and ordinary HTTP fetchers should remain unchanged by shared-specific challenge detection.
