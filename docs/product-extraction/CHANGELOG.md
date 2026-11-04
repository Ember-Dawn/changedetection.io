# Product extraction changes

## 2026-11 — Notification templates and product alert messages

- Added a copy-on-select notification template library (three presets and named custom templates) to existing global, Tag, and Watch editors. Saved templates hold only title/body/format; they never store destinations or change existing Watches until the normal Save action.
- Added a read-only preview endpoint with sample or saved Watch context; preview never calls Apprise or mutates Watch data. Real notifications still use the existing notification pipeline.
- Added product rule, human-readable reason, previous stock, reference price and signed amount to `purchase_alert` template variables, derived from stored event data rather than the display-oriented `restock.last_price`.
- Custom templates live in global `notification_templates` settings. The generic default notification message and Watch/Tag/global notification inheritance are unchanged.


## 2026-11 — Stock & Price policy expansion

- Added independent stock event/price event choices, current-stock price filters, AND (default) / OR, and cumulative percentage thresholds.
- Added price-first Watch/Tag form, continuation toggle (on by default), and copyable Markdown rule explanation sourced from `STOCK_PRICE_RULES.md`.
- Updated product notification tokens, API schema and regression tests. No old purchase-goal configuration migration is provided.
