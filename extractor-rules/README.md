# Product extraction rules (Git tracked)

- Files in `rules/*.json` are live executable **declarative rules** (no arbitrary JS or Python).
- `examples/*.json` documents the format but is not automatically applied.
- Import/edit/test through the authenticated `/product-extractors/` WebUI.
- Changes saved in WebUI modify files in this bind-mounted Git working tree; **Git commits are manual**.
- Use one Watch per website URL (and per store/locale where applicable). A Watch can choose `auto`, `rule`, or `builtin` extraction mode.
- `auto` selects one domain/path matching rule, or falls back to built-in restock metadata; ambiguity is an error.
- Explicit `rule` mode never silently falls back when extraction fails. Unknown stock is `null`, never automatically out-of-stock.
- Tests are read-only and do not commit Watch state, history, checksums, or notifications.
- Keep secrets and cookies out of these files; do not add arbitrary executable code to rule definitions.

Rules are loaded directly from the bind-mounted directory on each check, so updates do not require rebuilding the image. WebUI save does not `git commit`.

## Import workflow

1. Ask an AI to inspect the real product DOM, then generate a JSON rule following `schema/product-rule.schema.json`. The checked-in example uses placeholder selectors and should not be enabled unchanged.
2. Visit **Product Extractors** in the sidebar, import/paste JSON, and test against a URL or pasted HTML.
3. Save the rule, then open the Restock Watch's **Product purchase alerts** tab. Set extraction mode to **Selected rule only**, or **Auto**. Refresh the Watch editor to see newly imported rules in the dropdown.
4. When you change an active rule, the next check reprocesses even if the HTML is unchanged. The rule change is treated as a new extraction baseline, not a product-price alert.
5. `git diff -- extractor-rules` and `git add extractor-rules` on the host; commits are manual. Back up `datastore/` separately from Git rules.

## Rule enablement

Rules default to enabled; set `"enabled": false` in the JSON (then Save) to disable a rule. Disabled rules are ignored by automatic matching and rejected in explicit rule mode. A disabled rule can still be dry-run tested before re-enabling it.

## AI-assisted rule authoring

**Start with [`AI_RULE_GUIDE.md`](AI_RULE_GUIDE.md)** when asking another AI to generate rules from a real website's rendered HTML/DOM. The guide is self-contained: supported selector types, JSON fields, price/stock pitfalls, standard AI response format, and Dry Run workflow.

A complete, offline-testable pair is included in [`examples/sample-product.html`](examples/sample-product.html) and [`examples/sample-product-rule.json`](examples/sample-product-rule.json). These represent a **fictional demonstration website**, not selectors verified against any real retailer. Paste the HTML into WebUI's Dry Run and load the example rule to see the expected output. The basic `example-product.json` is a minimal structure only; do not deploy it against a real store without inspecting the real DOM.


V2: JSON 条件语法、Pickup/Shipping、多场景测试及合成示例请参阅 `AI_RULE_GUIDE.md`。

## Duplicate imports, updates and deletion

Rule identity is the stable, Git-friendly `id` (`rules/<id>.json`), not a UUID. Import only loads content into the editor. Saving an unchanged rule is a no-op. Editing the currently loaded ID saves directly with its last-seen revision; a new/imported/renamed rule that conflicts with another existing ID requires an in-page overwrite confirmation. Enter confirms and Escape cancels; all overwrites still require the matching last-seen content revision. If another editor or Git changed the rule, reload before retrying. Duplicate creates a new ID. Delete asks for confirmation and refuses a rule referenced by an explicit Restock Watch or by the auto-selection URL matching of a Restock Watch; first remove those dependencies. Deleting a file is a Git working-tree change; the WebUI does not execute `git commit`.

`Copy data` copies just the normalized product fields; `Copy full JSON` includes field diagnostics but excludes any screenshot.

## Watch purchase notification policy

JSON rules only extract product facts. The evaluator supports seven `price_mode` and six `stock_mode` choices, cumulative percentages, current-stock filters, and AND/OR where appropriate; first valid measurements establish baselines rather than sending alerts. See [Stock & Price rules](../docs/product-extraction/STOCK_PRICE_RULES.md), [events and dispatch](../docs/product-extraction/RESTOCK_AND_ALERTS.md), and [message templates](../docs/product-extraction/NOTIFICATION_TEMPLATES.md).

**Known audited mismatch (2026-11-04):** the old form/API files still mention `alert_mode` and `target_price`; the new evaluator expects `price_mode` and `stock_mode`. Do not assume the old API examples work without integration testing.

## Rule-dependent page wait (optional)

The JSON v1 registry accepts `"page": {"extra_wait_seconds": 5}`; value must be an integer from 0 to 30. This adds browser post-navigation wait before HTML/screenshot capture. Omit the property to preserve the existing behavior. New Stock & Price Watches use an explicit selected rule (automatically suggested by URL in Edit > Watch) or the built-in extractor. Existing rules and Watch bindings are not rewritten.

## Fixed currency (optional)

For a store with a known currency, `fields.currency` may be `{"literal": "USD"}` (or another recognized uppercase ISO 4217 code). This is mutually exclusive with selector extraction; there is **no selector fallback**. Existing rules without this option remain valid and unchanged. See `AI_RULE_GUIDE.md`.
