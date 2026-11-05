### Product Extractors save and custom confirmations (2026-11-05)

- Editing the currently loaded rule now sends a revision-checked overwrite directly, without an unnecessary confirmation. New/imported/renamed IDs that conflict with a different existing rule still require explicit confirmation.
- Replaced native confirmations for discard, conflicting overwrite and delete with an in-page dialog. Enter confirms, Escape cancels, Tab stays within the dialog, and focus returns to the triggering control.
- Backend overwrite and optimistic revision checks are unchanged; Watch bindings and rule IDs are not migrated.

## 2026-11-05 — Product Extractors: fixed currency literal

- `fields.currency` supports either existing selectors or a stand-alone `{"literal":"USD"}` object (recognized uppercase ISO 4217 code); mixing the two forms is rejected. No fallback behavior is added.
- All existing JSON rules and their extraction signatures remain unchanged unless edited. The evaluator reports fixed currency without querying the page.
- Updated runtime validation, JSON Schema, AI rule guide, README and focused regression tests. Existing Watch data and store rules are not migrated.

# Product extraction changes

## 2026-11-04 — Notification template cleanup and Telegram-safe product defaults

- Reduced built-ins from seven to six: removed the selectable foldable HTML preset, preserved existing copied Watch bodies and custom templates; reordered the six choices and renamed the Rich display label without changing its ID.
- New or explicitly converted product Watches get HTML Compact on first initialization only when uncustomized and all effective notification destinations are Telegram. Existing Watch notification settings remain untouched; other destinations keep generic defaults.
- Restored exact-match template selection in the editor without a new persisted template ID; selection and unsaved edits retain the Apply guard.
- Corrected outdated documentation that described already-integrated `price_mode` / `stock_mode` fields as missing from forms, processor and API schema. Historic changelog entries below remain historical.


This file records **historical** changes. Current behavior: [Stock & Price rules](STOCK_PRICE_RULES.md), [event/delivery evaluation](RESTOCK_AND_ALERTS.md), and [template guide](NOTIFICATION_TEMPLATES.md). The old mentions of three presets or old API schemas refer to earlier stages; they are not current instructions.

### Documentation consolidation and integration audit (2026-11-04)

- Reconciled current monitoring and Telegram template documentation; added `NOTIFICATION_TEMPLATES.md`, updated README and AI handoff links.
- Recorded the **unresolved** new purchase policy evaluator vs legacy form/processor defaults/API schema mismatch (`price_mode`/`stock_mode` versus `alert_mode`/`target_price`). No application integration fix is claimed in this documentation-only update.
- Current UI includes seven built-ins, dynamic Plain Text and three HTML product variants; actual Telegram/Docker acceptance still requires operator verification.


### Dynamic Telegram Rich product notification presentation (2026-11-04)

- The built-in Telegram Rich product preset now displays a linked Watch Title (no icon), with independent price and stock lines that are emitted only for enabled rules with reliable data.
- Price changes use a single comparison baseline and the format `$890.00 (−11%, ↓ $110.00)`; cumulative percentage alerts use their notification anchor, not the immediately preceding observation.
- Stock rows use `✅ In stock` / `❌ Out of stock` or triggered `✅ Restocked` / `❌ Sold out`, without an extra package icon. OR stock-only notifications may show an observed price change without claiming it triggered the alert.
- Extra rule, reason and formatted reference appear in `Details`, while test notifications suppress historical change claims. Existing stored custom templates and Watch body values are unchanged until users apply the updated preset.


### Template format selection, custom dialogs and HTML/Text presets (2026-11-04)

- Template selection changes Notification Format immediately; Apply changes Title/Body and normal Save persists. A pending guard prevents accidental mismatched format/body saves.
- Custom names support Chinese; template create/update/delete use app-styled dialogs, Enter confirmation and Escape cancellation (IME-safe).
- Seven built-ins now include Telegram HTML foldable, all details, compact, dynamic Plain Text, Rich, and generic presets.
- HTML product Body supplies an escaped linked title; internal Title is blank to avoid duplication. Templates reuse display tokens for stock-only, price-only, percentages, AND/OR.

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

## 2026-11 — Rule-based wait, editor matching and failure alerts

- Added optional `page.extra_wait_seconds` (0–30) to JSON Schema and runtime validator; browser fetch and rule Dry Run support the wait.
- Stock & Price alerts editor suggests uniquely matching rules by URL, preserving existing selections. Removed Auto from new choices; retained legacy backend support.
- Added extraction-only signatures to prevent waiting/metadata changes from rebasing stock/price tracking. Old signatures are adopted safely.
- Added first-failure/one-recovery operational notifications with delivery acknowledgement and later retry for failed delivery.
- Existing shop JSON files and Watches are not migrated.

### Product Extractors initial revision loading and 409 save fix (2026-11-05)

- Fixed first-page-load saves of existing JSON rules: the rule index and revision map are populated from the API before save is enabled. Previously this could submit `overwrite: false` and `expected_signature: null` for an existing Newegg rule, yielding HTTP 409.
- The save API now returns stable `RULE_ID_CONFLICT` and `RULE_REVISION_CONFLICT` codes. ID collisions can display the existing custom Overwrite dialog; changed revisions require reloading instead of silently overwriting.
- Added a revision parameter to the Product Extractors JavaScript URL to avoid stale browser cache and removed outdated Auto-mode wording. Added Node DOM/fetch behavioral tests and updated Python contract checks. Watch data and extraction rules are not migrated.

### Collapsible notification Rendered / Raw preview (2026-11-05)

- Replaced the large fixed preview display with a collapsible, content-sized panel and a scroll limit for long messages.
- Added Rendered (safe format-aware view for Text, HTML, Telegram HTML, Markdown/MarkdownV2 and supported Rich blocks) and Raw (post-Jinja2 title/body) tabs. No Telegram bubble simulation or actual send.
- Added stale preview indicators, overlapping-request protection, unsupported Rich warnings, and conservative URL/tag validation. Existing notification destinations, templates and Watch state are unchanged.
