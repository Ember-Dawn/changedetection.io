# Product extraction changes

### Dynamic Telegram Rich product notification presentation (2026-11-04)

- The built-in Telegram Rich product preset now displays a linked Watch Title (no icon), with independent price and stock lines that are emitted only for enabled rules with reliable data.
- Price changes use a single comparison baseline and the format `$890.00 (−11%, ↓ $110.00)`; cumulative percentage alerts use their notification anchor, not the immediately preceding observation.
- Stock rows use `✅ In stock` / `❌ Out of stock` or triggered `✅ Restocked` / `❌ Sold out`, without an extra package icon. OR stock-only notifications may show an observed price change without claiming it triggered the alert.
- Extra rule, reason and formatted reference appear in `Details`, while test notifications suppress historical change claims. Existing stored custom templates and Watch body values are unchanged until users apply the updated preset.


### Template format selection, inline dialogs and dynamic Telegram HTML/Text presets (2026-11-04)

- Selecting a saved or built-in notification template now changes the Notification Format immediately, but leaves Title/Body untouched until **Apply to editor**. A guarded page Save prevents accidentally storing a format with an un-applied old body.
- Replaced template-library browser prompt/confirm interactions with one keyboard-accessible app-styled dialog. Enter confirms (except during IME composition), Escape cancels, and asynchronous template errors stay visible in the dialog. Existing UTF-8/Chinese template names remain supported (maximum 100 Unicode code points).
- Retained the foldable Telegram HTML preset and added **HTML (all details)** (expanded inline), **HTML (compact)** (only linked title, price and stock, with no rules/reason/details), and dynamic **Product · Plain Text** presets.
- All product format presets use the `purchase_alert` presentation tokens for price-only, stock-only, percentage and combined modes. HTML product bodies render an escaped clickable title (`watch_open_url`/`watch_url`), with a deliberately empty rendered Notification Title to prevent Apprise duplicating or escaping the link; plain text includes the raw URL. Test notifications avoid reporting stale historical deltas as current events.
- Built-in preset changes do not overwrite Watch/Tag/Global notification bodies or saved custom templates. Reapply the chosen preset and save the form to use it. Live Telegram/Apprise delivery and interactive browser acceptance still need verification on the user's deployment.

## 2026-11 — Notification templates and product alert messages

- Added a copy-on-select notification template library (three presets and named custom templates) to existing global, Tag, and Watch editors. Saved templates hold only title/body/format; they never store destinations or change existing Watches until the normal Save action.
- Added a read-only preview endpoint with sample or saved Watch context; preview never calls Apprise or mutates Watch data. Real notifications still use the existing notification pipeline.
- Added product rule, human-readable reason, previous stock, reference price and signed amount to `purchase_alert` template variables, derived from stored event data rather than the display-oriented `restock.last_price`.
- Custom templates live in global `notification_templates` settings. The generic default notification message and Watch/Tag/global notification inheritance are unchanged.


## 2026-11 — Stock & Price policy expansion

- Added independent stock event/price event choices, current-stock price filters, AND (default) / OR, and cumulative percentage thresholds.
- Added price-first Watch/Tag form, continuation toggle (on by default), and copyable Markdown rule explanation sourced from `STOCK_PRICE_RULES.md`.
- Updated product notification tokens, API schema and regression tests. No old purchase-goal configuration migration is provided.

### Rich template internal title normalization (2026-11-04)

- Rich Message templates always store `{{ watch_title }}` as their internal `title`, for built-in templates and custom template creation/updates; a missing or stale hidden title is ignored. The visible Telegram title stays in the Rich JSON `heading`.
- Applying a Rich template fills the hidden title with the same internal value. Normal notification formats keep editable titles. Existing stored Rich templates are normalized when listed without changing existing Watch settings.

### Telegram notification format and product template update (2026-11-04)

- Added Telegram HTML, MarkdownV2, and JSON-block Rich Message format choices to the existing Notification Format field.
- Moved the format selector beside the notification template selector. Applying a template copies its title, body, and format; the normal page Save remains necessary.
- Added two built-in Telegram product presets: HTML with expandable blockquote and Rich JSON with details. Both prioritize watch title, formatted price, stock and product URL; rules and trigger explanation appear in details.
- Added a Telegram-only Rich Message adapter using private short-lived JSON template files and existing Apprise destinations. A format selected for non-Telegram destinations is rejected instead of silently sending Rich JSON to unrelated services.
- Telegram-specific sending requires a real Docker/Apprise/Telegram smoke test. No UI-rendering or real Telegram delivery acceptance has been claimed in the offline checks.
