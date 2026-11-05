# Product purchase alerts: evaluation and notification delivery

This document explains **event and delivery behavior**. The authoritative configuration and edge cases are in [STOCK_PRICE_RULES.md](STOCK_PRICE_RULES.md); template formats, previews and editor behavior are in [NOTIFICATION_TEMPLATES.md](NOTIFICATION_TEMPLATES.md). Extraction rule authoring is separate: see [AI_RULE_GUIDE.md](../../extractor-rules/AI_RULE_GUIDE.md).

## Configured monitoring policy

The rule evaluator is `changedetectionio/processors/restock_diff/purchase_alert.py`. The intended policy uses:

| Setting | Supported values / role |
| --- | --- |
| `price_mode` | `none`, `below`, `above`, `any_change`, `percent_down`, `percent_up`, `percent_any` |
| `stock_mode` | `none`, `in_stock`, `out_of_stock`, `restock`, `sold_out`, `any_change` |
| `price_threshold` | Strict target for `below`/`above`, or positive percentage for percent modes |
| `price_follow_changes` | Defaults on for fixed targets: later changes within the qualified range notify |
| `combine_mode` | `and` (default) or `or` for combinations with a stock **event** mode |

The current-stock options (`in_stock`, `out_of_stock`) are filters for price rules, not stand-alone event notifications, and cannot use OR. `restock`, `sold_out`, and stock `any_change` require confirmed transitions. A fixed threshold uses strict inequality; equal-to-target values do not qualify. For percentages, small changes accumulate against a persistent anchor instead of comparing only with the immediately previous check. The anchor advances only when the percentage condition participates in an alert.

## Reliable baselines and events

- The **first reliable measurement establishes the baseline, without alerting**. Changing the configured policy or semantically significant extraction fields also rebaselines; page wait and descriptive metadata changes do not.
- A missing/invalid price must not be treated as zero; unknown stock (`null`) must not be interpreted as in stock or out of stock. Missing inputs never fabricate a change or transition.
- Known currency changes prevent unsafe cross-currency price comparisons. A reliable stock event may still qualify under OR.
- The Watch saves event-specific comparison details in `purchase_alert_state` separately from the current display data in `restock`.
- Stock quantity changes alone do not count as availability transitions unless the derived `in_stock` boolean changes.

### Combination behavior

**AND:** Both conditions must hold within the same effective check. For fixed price thresholds the current price being in range is sufficient when paired with a stock event; for `any_change` or percentage modes, a matching price event is required. A stock current-state filter always gates a price rule.

**OR:** A new price event **or** stock transition suffices. If both trigger in the same check, produce one notification with a combined reason. Merely remaining under or over a fixed target is not a fresh OR price event.

| Example | Expected event |
| --- | --- |
| Below $1,300, currently in stock; price $1,400 → $1,200 | Price qualified with stock filter satisfied |
| Below $1,300; price $1,200 → $1,350 | Leaving range; no price alert |
| Stock-only `restock`; known out of stock → in stock | Restock alert, no price needed |
| Percentage down 10%; anchor $1,000 → $970 → $890 | Cumulative −11%, a qualifying price event |
| Restock **OR** price down 10%; stock restocks while price drops only 3% | Stock-only trigger; do not claim the 10% price threshold matched |
| Any price change **OR** any stock transition; both change | One notification reporting both causes |
| First successful check, or only unknown inputs | Baseline or preserved state; no fabricated event |

## Notification data and dispatch

`changedetectionio/processors/restock_diff/__init__.py` builds readable `purchase_alert` notification variables from the stored evaluator state, including `show_price`, `show_stock`, `display_price`, `display_change`, `display_stock`, `display_stock_current`, `display_reference_price`, `rule_text` and `reason_text`.

The display form `$890.00 (−11%, ↓ $110.00)` uses **one comparison baseline** for its percentage and absolute amount. In an OR event, price movement may be displayed even when only stock triggered; the `reason_text` must distinguish the actual trigger. Test notifications should not imply the purchase rule actually matched.

The existing Worker/notification service and Apprise pipeline continue to gate and deliver notifications. Enqueueing does not guarantee arrival or exactly-once delivery. Preview is read-only, uses saved Watch context or sample data, and never queues a notification. Template choices are described in [NOTIFICATION_TEMPLATES.md](NOTIFICATION_TEMPLATES.md).

## Watch/Tag/API end-to-end validation outstanding — audited 2026-11-04

**Source alignment (reviewed 2026-11-04):** `forms.py`, `processor.py`, and `api.yaml` now use `price_mode`, `stock_mode`, `price_threshold` and related expanded rule fields. Earlier notes claiming these files still used legacy `alert_mode` / `target_price` were out of date. Legacy stored configurations are not automatically migrated; revalidate the live deployment and test the complete rule path after upgrades.

The extraction modes are `auto`, `rule` and `builtin`; rule Dry Run does not modify Watch history or alert baselines. Confirm Tag `overrides_watch` behavior and legacy stored configuration handling on the actual deployed revision; the previous field-name mismatch claim is obsolete.

## Maintenance and verification

Relevant paths are `purchase_alert.py` (policy), `restock_diff/__init__.py` (display tokens), `notification_service.py` (dispatch), and the template/Telegram handler. Run the product presentation and Telegram format/contract tests, plus real browser/Telegram acceptance tests after deploying. The policy tests exercise the evaluator but cannot substitute for full WebUI/API and live Telegram acceptance testing. Never describe offline JSON/Jinja2 validation as successful Telegram delivery.

## Rule failure notifications

The first selected-rule extraction/configuration failure is queued as an operational alert. A successfully delivered failure message is not repeated while the rule remains broken. A successful later extraction queues one recovery notification. If delivery fails, the alert remains eligible for retry on subsequent checks. Telegram-only destinations use a linked product title in HTML; non-Telegram or mixed destinations get a short plain-text message with the URL. These messages do not use the normal price/stock notification template. Paused Watches do not check.
