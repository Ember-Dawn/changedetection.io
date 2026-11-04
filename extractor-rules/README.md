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
3. Save the rule, then open the Restock Watch's **Restock & Price Detection** tab. Set extraction mode to **Selected rule only**, or **Auto**. Refresh the Watch editor to see newly imported rules in the dropdown.
4. When you change an active rule, the next check reprocesses even if the HTML is unchanged. The rule change is treated as a new extraction baseline, not a product-price alert.
5. `git diff -- extractor-rules` and `git add extractor-rules` on the host; commits are manual. Back up `datastore/` separately from Git rules.

## Rule enablement

Rules default to enabled; set `"enabled": false` in the JSON (then Save) to disable a rule. Disabled rules are ignored by automatic matching and rejected in explicit rule mode. A disabled rule can still be dry-run tested before re-enabling it.
