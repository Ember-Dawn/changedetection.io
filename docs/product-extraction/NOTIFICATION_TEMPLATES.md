# Notification templates and Telegram product messages

This is the current notification-template specification (2026-11-04). Monitoring policy is in [STOCK_PRICE_RULES.md](STOCK_PRICE_RULES.md), with event/delivery semantics in [RESTOCK_AND_ALERTS.md](RESTOCK_AND_ALERTS.md).

## Library and current presets

Templates store a `name`, `title`, `body` and `format` (custom templates also have an ID). They do **not** store destination URLs and are not permanently linked to Watches. Custom templates live in `settings.application.notification_templates`; there are at most **50** saved custom entries. Names may contain Chinese and other Unicode text, are nonempty, and are limited to **100 Python Unicode code points**.

| Built-in preset | Format | Contents |
| --- | --- | --- |
| General webpage change | Generic default | Original generic notification |
| Product · Plain Text | `text` | Price/stock, inline rule/reason/reference, raw product URL |
| Compact change alert | `text` | Generic compact Watch/diff/link message |
| Telegram product · HTML (compact) | `telegram_html` | Clickable title and dynamic price/stock, without auxiliary details |
| Telegram product · HTML (all details) | `telegram_html` | Clickable title, price/stock, rule/reason/reference inline |
| Telegram product · Rich (all details) | `telegram_rich` | Linked Watch heading (size 5), price/stock rows, native Details block |

Six built-ins are listed in their display order. The removed `builtin-product-html` foldable preset is no longer selectable. Existing Watches containing a copied foldable body are not migrated or modified; custom templates are also untouched. The Rich preset retains ID `builtin-product-rich` despite its display name changing.

### Default for new product Watches

The single source of truth is `notification.templates.apply_product_notification_defaults`. On creation with `processor=restock_diff`, or on an existing Watch's explicit switch to that processor, the app copies `builtin-product-html-compact` **only if** the Watch still uses default/empty title, body and format, no notification field was explicitly supplied during creation, and **all effective notification URLs** are `tgram://` destinations. Effective targets resolve Watch, then first non-muted Tag, then Global. If the target list is empty, non-Telegram or mixed, existing generic defaults remain. A custom title/body/format, or an explicitly submitted notification field, always takes precedence.

This is one-time initialization, not a permanent template reference. The system does not migrate existing product Watches on startup or when global notification destinations are changed. An exact Title/Body/Format match may be displayed as the selected template in the UI, but the Watch stores only the copied values; a manual edit clears a no-longer-matching UI selection.

## Selecting, applying and saving

1. Open **Customise notifications** in the Global, Tag or Watch editor.
2. Choosing **Notification template** updates **Notification Format immediately**, but does **not** overwrite Title or Body. The selected template is pending application.
3. Click **Apply to editor** to populate Title, Body and Format. Only the normal page **Save** commits the notification settings. A pending selection blocks saving a mismatched format with the previous body.
4. Create/update/delete dialogs are app-styled instead of native `prompt`/`confirm`. Enter confirms (except during IME composition), Escape cancels, and invalid name/server errors remain visible in the dialog. Chinese template names are supported.
5. Editing a custom library template does not automatically update saved Watch/Tag/Global notification bodies. Reapply the desired preset and Save the form.

For Rich format, **Notification Title** is hidden visually but the input remains enabled for form submission. The internal Rich title is normalized to `{{ watch_title }}` when templates are saved/listed; the **visible** heading lives inside the Body JSON. HTML product presets deliberately have a Jinja2-empty internal Title (`{{ "" }}`) because their Body already contains a clickable heading; this avoids a duplicated Apprise title. Do not replace the normal textarea with a bespoke structured JSON editor.

## Dynamic rendering

`changedetectionio/processors/restock_diff/__init__.py` provides these presentation values:

| Token | Meaning |
| --- | --- |
| `purchase_alert.show_price` | Show a price row only when price monitoring is on and valid price data exists |
| `purchase_alert.show_stock` | Show a stock row only when a stock rule/filter is on and status is known |
| `purchase_alert.display_price` | Current formatted price, e.g. `$890.00` |
| `purchase_alert.display_change` | Same-baseline signed percent and amount, e.g. `(−11%, ↓ $110.00)` |
| `purchase_alert.display_stock` | `✅ In stock`, `❌ Out of stock`, `✅ Restocked`, or `❌ Sold out` |
| `purchase_alert.display_stock_current` | Current-state label for **test notifications**, without false transition claims |
| `purchase_alert.rule_text` | Human-readable full rule, including AND/OR where applicable |
| `purchase_alert.reason_text` | Saved event cause; distinguishes actual trigger(s) from other observed conditions |
| `purchase_alert.display_reference_price` | Formatted comparison reference, when valid |
| `purchase_alert.price_mode`, `.stock_mode`, `.combine_mode` | Monitoring settings, **not** replacement policy evaluator |
| `watch_title`, `watch_open_url`, `watch_url` | Name and click destination |
| `test_notification` | Display a test explanation, avoiding stale historical change/reference claims |

This supports price-only (hide stock), stock-only (hide price), percentage-based rules (cumulative anchor), AND filters, OR events, and simultaneous events. Missing values should result in omitted rows rather than invented values. Templates only render results; never recalculate when an alert should fire.

## Telegram formats and links

| Format | Clickable title | Details |
| --- | --- | --- |
| Plain Text | No hidden-URL hyperlink. Show the URL separately; clients may auto-link it | Inline with emoji |
| Telegram HTML | HTML `<a href="..."><b>title</b></a>` generated in Body, with escaped title and attribute | All details inline or **compact with none** |
| Telegram Rich | Typed RichText `url` inside a size-5 `heading` | Native `details` block |
| Telegram MarkdownV2 | Valid escaped MarkdownV2 links can be used | No built-in dedicated product preset |

`💰`, `✅`, `❌`, `🎯`, `🔔` and `📊` are ordinary Unicode emoji, not Rich-only icons. Rich `details` and HTML expandable blockquotes are Telegram-specific; client spacing, heading size and fold controls are not freely CSS-customizable. Rich product title has **no shopping-cart emoji** or separate `View product` row. The stock state has no extra 📦 icon.

Telegram-specific formats (`telegram_html`, `telegram_markdownv2`, `telegram_rich`) require a `tgram://` destination. Rich JSON is validated, sent through Apprise's private temporary `template` file, and cleaned up after sending; it is not transmitted as literal JSON text. Real Telegram client behavior must be verified with a test send.

## Preview, tests, maintenance

The preview route at `changedetectionio/blueprint/ui/notification.py` is **read-only**; it never sends notifications or mutates Watch state. Global/Tag preview uses examples and Watch preview uses saved Watch state. Render previews as text to avoid treating untrusted product content as HTML. A passing preview is not evidence of successful Telegram delivery.

Implementation map: `notification/templates.py` (presets and storage); `static/js/notifications.js` and notification form templates (UI/keyboard/pending guard); `notification/telegram_formats.py` and `notification/handler.py` (Telegram); `processors/restock_diff/purchase_alert.py` (event evaluator); `processors/restock_diff/__init__.py` (presentation tokens). Exercise only-price/only-stock, percentages, AND, OR, unknown input, test notifications, name validation/IME behavior, HTML escaping, Rich JSON parsing, and one real Telegram send after deploying.

## Selected-product-rule failure and recovery messages

These are operational status notifications, **not** an additional editable built-in template. They reuse the Watch/Tag/system notification destination cascade, not the Watch's commodity price/stock body. The first failed selected-rule extraction alerts immediately; subsequent failures do not repeat after confirmed delivery; the first successful recovery sends a second alert. A Telegram-only destination receives an HTML hyperlink on the product title; mixed/other channels receive a short text notice with the product URL. Transport errors are retried on future checks.
