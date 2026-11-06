# Watch Health and product fetch reliability

## Purpose

The monitoring transport, health accounting, and business notification pipeline are separate.
A **page attempt** fetches one page; a **check** can contain multiple bounded page attempts;
only a completed check affects consecutive failure counts. Commodity price/stock notifications
retain their existing processor and purchase-alert evaluation contracts.

## Settings

Global defaults live in `settings.requests`, edited under **Settings → Fetching**.
Individual product Watches can override them under **Edit → General** by disabling
**Use global product reliability settings**. Missing individual overrides fall back to
current global values. Settings are bounded on both the form and runtime boundaries:

| Key | Default | Allowed | Meaning |
| --- | --- | --- | --- |
| `reliability_wait_seconds` | 10 | 0–30 | Max additional wait for valid required rule data on the SAME shared CloakBrowser tab. |
| `reliability_page_attempts` | 2 | 1–3 | Maximum sequential tab attempts in one check. |
| `reliability_page_gap_seconds` | 10 | 0–60 | Gap before opening a fresh tab after a transient error. |
| `reliability_failure_threshold` | 2 | 1–10 | Completed failed checks before `failed`. |
| `reliability_retry_minutes` | 5 | 0–1440 | Accelerated check interval, 0 disables it. |

The same-tab readiness hook operates *inside* the manager's upstream extraction wait
seam, checking the **selected declarative product rule** for the fields demanded by the
Watch configuration. It returns early on valid values. Unselected or built-in-only
extraction does not get rule-aware DOM polling. A transient product-rule failure,
connection error, timeout or empty reply may get a new tab, **only** for scheduled
`restock_diff` checks using `html_cloakbrowser_shared` without Browser Steps.
The original persistent Browser Context and Profile remain shared, and each page is
closed via the upstream managed Page lease. Manual browser/preview and Live Browser
control do not acquire product-readiness settings or enable automatic tab retries.

A recognized verification bypasses ordinary retry and uses the existing verification
notifier. The automated tab closes via normal fetch cleanup; the operator can open
its URL in a separate manual-control tab of their choice. No existing challenge tab
needs to remain open. Completing the challenge alone never marks a check successful:
only a later successful page extraction clears attention status. Normal scheduled
checks continue; accelerated failure rechecks are disabled during `action_required`.

## Health model

`watch.watch_health` (persisted) stores: `status`, `consecutive_failures`,
`next_retry_at`, `last_error`, `error_category`, `last_success_at`,
`status_changed_at`. Values are `unknown`, `healthy`, `degraded`, `failed`,
`action_required`; user pause remains a separate scheduling setting.

- An entire logical check failing increases the counter once.
- A completed successful check resets count and retry timestamp.
- Confirmed verification means `action_required` and no accelerated retries.
- The scheduler respects the original watch/global schedule, min-interval gate,
  paused watches, running/queued UUID deduplication, proxy reuse limits, and
  Live Browser admission gate before admitting accelerated checks.
- `next_retry_at` is persisted; restarts do not reset the schedule.
- All completed normal checks (including no-change checksum fast path) must use the
  unified state machine. Never call recovery logic unconditionally on a handler's
  existence; recovery requires successful processing.

`watch.watch_health_alert` is a separate persistent event/delivery state; the
Notification worker verifies event freshness, reports transport acknowledgements,
and retries on subsequent checks (minimum 300s and pending timeout 600s).
No human-visible claim of guaranteed exactly-once Telegram delivery is made.
Recognized challenges continue using the preexisting special verification notifier.
Operational product-rule errors use **only** Watch Health. The former standalone `product_rule_alerts.py` notifier and its detached
legacy tests have been removed. Product-rule check failure and recovery now use
only the Watch Health lifecycle; old alert state is not migrated. Commodity price/stock alerts remain separate.
A confirmed failure is assigned `failure_id`; only its successfully acknowledged
failure event authorizes a recovery. Queued stale failure events are invalidated on
success or recognized verification. Apprise `False` counts as delivery failure for
Watch Health as well as verification notices. Delivery is best effort; strict
exactly-once external delivery is not guaranteed.

## Integration contracts

- `watch_health.manager.policy(datastore, watch)`: validated effective setting lookup.
- `watch_health.manager.record_result(...)`: single outcome transition per check.
- `watch_health.alerts.on_result(...)`: health-only alert transition.
- `watch_health.manager.retry_due(...)`: scheduler integration.
- `perform_reliable_product_check`: at most N attempts, still one Watch check.
- `product_ready.PRODUCT_READINESS`: scoped ContextVar on BrowserManager's event loop.

**No second Context or Chromium process** must be opened. BrowserManager still owns
Playwright objects and Page close acknowledgement. Error or cancellation must not
produce false price/stock transitions, false recovery, or false monitoring history.

## Acceptance checklist

- Form defaults, bounds and Watch overrides work after reload and Docker restart.
- Page data appearing during extra wait ends the wait early, and no new tab opens.
- The old tab is closed before opening a replacement on a transient failure.
- The configured gap and attempt limit are respected.
- Two failed full checks (not two tab attempts) confirm a failure.
- Accelerated recheck uses the independent `next_retry_at`, and normal interval
  returns after success.
- Cloudflare/Google verification stops normal retries and can be resolved in
  separately opened manual control tab.
- Watch health alert deduplication/transport acknowledgements persist across restart.
- Existing purchase notification conditions/templates are not modified.

Unit tests cover pure health transitions and defaults. Real shared-CloakBrowser
navigation, Watch/Tag configuration, explicit browser steps, HTTP failure modes,
notification delivery and live-mode handoff require a Docker integration run.

## Operational notification presentation (2026-11-06)

Watch Health notifications are `⚠️ 监控异常` and `✅ 监控已恢复`.
All-Telegram destinations use `telegram_html` with an HTML-escaped, clickable Watch
name and short error; mixed destinations fall back to plaintext. Long signed URL
query strings are not embedded in the notification body. HTTP 4xx/5xx status is
shown as a short code. Explicit Cloudflare/Google challenges use their dedicated
Quick Verify notification, never simultaneous generic health alerts.

On successful delivery, `watch_health_alert.notified` is tied to the confirmed
`failure_id`. An unsuccessful delivery is not acknowledged; a subsequent success
instead clears that unsent incident without sending a recovery notice.
