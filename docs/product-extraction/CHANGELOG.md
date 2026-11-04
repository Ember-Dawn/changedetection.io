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

### Telegram notification format and product template update (2026-11-04)

- Added Telegram HTML, MarkdownV2, and JSON-block Rich Message format choices to the existing Notification Format field.
- Moved the format selector beside the notification template selector. Applying a template copies its title, body, and format; the normal page Save remains necessary.
- Added two built-in Telegram product presets: HTML with expandable blockquote and Rich JSON with details. Both prioritize watch title, formatted price, stock and product URL; rules and trigger explanation appear in details.
- Added a Telegram-only Rich Message adapter using private short-lived JSON template files and existing Apprise destinations. A format selected for non-Telegram destinations is rejected instead of silently sending Rich JSON to unrelated services.
- Telegram-specific sending requires a real Docker/Apprise/Telegram smoke test. No UI-rendering or real Telegram delivery acceptance has been claimed in the offline checks.
