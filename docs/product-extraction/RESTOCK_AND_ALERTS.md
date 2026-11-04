# Product purchase alerts: rules, qualification, and notifications

This document is the source of truth for the fork's **Restock & Price** watch behavior as of November 2026. The UI calls this **Product purchase alerts**. Browser extraction and JSON rule authoring are separate concerns: see [`../../extractor-rules/AI_RULE_GUIDE.md`](../../extractor-rules/AI_RULE_GUIDE.md).

## Three monitoring goals

| `alert_mode` | Requirement | Price alerts while qualified |
| --- | --- | --- |
| `stock_and_price` | `in_stock is True` **AND** `price < target_price` | Every price change, **up or down**, as long as the new price is still below the target |
| `stock_only` | `in_stock is True` | None; only notify when returning from confirmed out-of-stock |
| `price_only` | `price < target_price`, regardless of stock | Every price change, up or down, as long as the new price is still below the target |

The price comparison is **strictly less than**, not less-than-or-equal. A `target_price` is required in `stock_and_price` and `price_only`. Do not set `follow_price_changes`, `in_stock_processing`, `price_change_min/max` or `price_change_threshold_percent`: those are fields from the removed legacy notification policy.

## Baselines, changes and duplicate prevention

- The **first valid evaluation creates a baseline, with no notification**, even if it is already in the desired state. The regular Worker and notification service are not modified to send first-check notifications.
- A subsequent transition from a known unqualified state to qualified generates an alert.
- While still qualified in either price-based mode, **any different valid price** generates another alert, including *increases* below the target. The price is compared with the last reliable **qualified** price (stored as a decimal string); equal price generates no alert.
- While qualified in `stock_only`, price changes do not matter; the next alert requires a confirmed out-of-stock transition followed by in-stock.
- If the price reaches or exceeds the target, or the product is confirmed out-of-stock in `stock_and_price`, the state becomes unqualified and no alert is sent. A future valid requalification triggers another alert.
- Extraction failures, captcha pages, `in_stock: null`, and missing prices are **not false/out-of-stock**. The previous reliable condition and price remain; the next valid observation resumes comparison. When one known false condition is sufficient (e.g. confirmed out of stock), a missing unrelated field may still establish an unqualified state.
- A change to the monitoring mode or target price begins a fresh baseline; a JSON extraction-rule signature change also rebaselines. Merely editing the target is not a product price-change event.
- If a previously known currency changes (for example USD to EUR), the evaluator marks the result unknown and does not compare prices across currencies. Correct the extraction rule and target denomination before relying on notifications.
- This uses the existing Watch `purchase_alert_state`, `restock` and snapshot persistence. There is no new SQL database, no separate schedule, and no change to shared CloakBrowser page/session behavior.

### Example: in-stock AND less than $1,300

| Previous check | Current check | Notify? | Reason |
| --- | --- | --- | --- |
| First valid check | In stock, $1,250 | No | Baseline; user explicitly opted out of initial alerts |
| In stock, $1,250 | In stock, $1,100 | Yes | Price decreased while qualified |
| In stock, $1,100 | In stock, $1,200 | **Yes** | Price increased but still below $1,300 |
| In stock, $1,200 | In stock, $1,200 | No | Same price |
| In stock, $1,200 | In stock, $1,350 | No | Exceeds target |
| In stock, $1,350 | In stock, $1,250 | Yes | Requalified |
| In stock, $1,250 | Out of stock, $1,100 | No | Cannot purchase |
| Out of stock, $1,100 | In stock, $1,100 | Yes | Requalified |
| In stock, $1,250 | Unknown stock, $1,100 | No | Cannot confirm availability |

## JSON rules vs purchase policies

The Git-tracked extraction rule (CSS, XPath, JSONPath and conditions) determines the fields `in_stock`, `pickup`, `shipping`, `price`, `currency`, `stock_quantity`, and SKU. The **Watch** chooses the purchase policy. To only track store pickup, make the JSON rule compute `in_stock` from its `pickup` field. To include shipping, compute `in_stock` from `pickup OR shipping`. Changes in stock quantity alone do **not** trigger a notification unless they change `in_stock` or a qualifying price changes.

## Configuration in Watch editor

1. Add a single product URL with the **Re-stock & Price** processor and choose the supported browser backend.
2. Open **Product purchase alerts** and choose one of the three goals.
3. For price goals enter `Target price`, e.g. `1300`; value equal to target does not qualify. Stock-only needs no target.
4. Under **Product extraction mode**, choose `Selected rule only` then a `name — id` rule (such as `Micro Center Products — microcenter-products`), or select `Auto`/`Built-in`.
5. Save, run a check to establish the baseline, and inspect the Watch's extracted price/stock. Product Extractors Dry Run is read-only and does not affect notifications.

Notification templates can refer to `{{purchase_alert.reason}}`, `{{purchase_alert.mode}}`, `{{purchase_alert.target_price}}` alongside `{{restock.price}}` and `{{restock.in_stock}}`. Reasons include `became_qualified` and `price_changed`. The reason is saved by the Watch evaluator, not inferred from a chat or scraping screenshot.

A Group tag with `overrides_watch` can override the monitoring policy. The editor warns when this applies. API clients use `processor_config_restock_diff` with fields `alert_mode`, `target_price`, `extraction_mode`, and `extraction_rule_id`, as documented in `changedetectionio/processors/restock_diff/api.yaml`.

## Existing notification delivery limitations

This fork continues to use the existing Worker history/notification gating and Apprise queue. Only an **established** Watch emits normal content-change notifications; enqueueing a notification does not guarantee delivery or exactly-once semantics. The policy evaluator records alert reasons in `purchase_alert_state`, but does not alter Worker retry/delivery behavior. Telegram/Apprise URL and notification templates remain configured in the existing Watch/Tag notification tab.

## Testing and maintenance

The policy evaluator is `changedetectionio/processors/restock_diff/purchase_alert.py` and its standalone offline regression suite is `tests/product_extraction/test_purchase_alert.py` (`python -m unittest discover -s tests/product_extraction -p test_purchase_alert.py`). Run the existing Product Extractors and manual browser suites too. Real retailer checks, actual Playwright/CloakBrowser screenshot behavior, HTML parse paths, Watch notification queue, and Telegram delivery still require deployment-level tests. The first evaluation after applying this patch creates the **new-policy baseline** for existing Restock Watches.
