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

`verification_alerts.py` tracks two distinct watch fields:

- `manual_attention_reason`: known challenge type currently observed.
- `manual_attention_notified_reason`: the challenge type for which an alert was successfully **queued**.

This distinction lets the next check retry enqueueing if there were no configured notification URLs earlier. When a normal fetch and watch processing succeed, the challenge state is cleared; a recovery alert is only attempted if the initial alert had previously been queued. Repeated identical challenges should not spam Telegram. A change from one recognized challenge type to another may require a new alert.

**Queued ≠ delivered.** Actual Telegram delivery depends on correct Apprise URLs and the notification worker. In a failure report, inspect the watch's effective notification configuration, muted flags, notification worker logs, and the actual `last_error`. A `FilterNotFoundInResponse` warning in the UI alone does not prove the challenge classifier ran. The user previously observed Google Scholar filter errors without a Telegram alert; this motivated early detection plus fallback, but remote-site variants must still be tested in the deployed container.

Watch state is not a user pause. Scheduler retries at its configured cadence; for challenge-prone websites prefer a sensible interval rather than aggressive rechecking. Preserve last successful content while the challenge remains.

## Test matrix for maintainers

1. Ordinary Google Scholar page (no false alarm) and Chinese-language Scholar verification page (first alert).
2. Ordinary Micro Center product page and Cloudflare `Performing security verification` page (first alert).
3. Repeated same challenge: no additional alert.
4. Challenge with no notification URL configured: status recorded; once configured, a later check may enqueue it.
5. Recovery: a truly successful check clears the state and queues one recovery notice if an initial alert had been queued.
6. An unknown challenge page: normal error handling, no fabricated verification alert.
7. Add Watch preview must show screenshot without challenge-specific extra waiting and must not save challenge content as a baseline.
8. Use a real Telegram test endpoint only with operator approval; mock tests cannot prove message delivery.

The original independent `html_cloakbrowser` backend and ordinary HTTP fetchers should remain unchanged by shared-specific challenge detection.
