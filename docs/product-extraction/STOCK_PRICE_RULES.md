# Stock & Price monitoring rules

This file is the source for the expandable, copyable Markdown help embedded in the Watch/Tag editor.

## 1. Price first

| `price_mode` | Meaning |
| --- | --- |
| `none` | No price monitoring. |
| `below` | Price strictly below `price_threshold`. |
| `above` | Price strictly above `price_threshold`. |
| `any_change` | Any change between reliable prices, in either direction. |
| `percent_down` | Cumulative decrease of at least `price_threshold` percent. |
| `percent_up` | Cumulative increase of at least `price_threshold` percent. |
| `percent_any` | Cumulative absolute increase/decrease of at least the specified percent. |

For `below` and `above`, `price_follow_changes=true` **by default**: after entering the qualified range, each later price change **within** that range alerts (up or down). Disable to notify only on entry/re-entry. Leaving the qualified range does **not** send a price alert. Equal price and a price equal to the strict threshold do not alert.

Percentage changes use a persistent comparison anchor; small changes accumulate rather than comparing only with the immediately preceding check. An anchor advances only when the percentage condition actually participates in an emitted alert. Percent input must be positive; decreases cannot exceed 100%, while increases can exceed 100%. A base price of zero is not a percentage comparison anchor.

## 2. Stock second

| `stock_mode` | Meaning |
| --- | --- |
| `none` | Ignore stock. |
| `in_stock` | Current stock is true; **price-only filter**. |
| `out_of_stock` | Current stock is false; **price-only filter**. |
| `restock` | A confirmed `false -> true` transition. |
| `sold_out` | A confirmed `true -> false` transition. |
| `any_change` | Either confirmed stock transition. |

The two current-state filters are available only when price monitoring is enabled; they always gate price notifications and **do not** have an OR setting (the API also rejects OR with a current-stock filter). Without a price rule, use restock/sold-out/any-change instead.

## 3. Combination

With a price rule and a stock **event** rule (restock/sold-out/any-change), `combine_mode=and` is the default; `or` is optional.

- **AND:** the stock transition and price condition both hold in the *same effective check*. When price mode is `below` or `above`, current price qualification is enough; it does not also need to cross the price threshold. For `any_change` and percentage modes, a corresponding price event must occur in that check.
- **OR:** either the stock event or a fresh price event triggers; two matches in one check produce one notification with a combined reason. A price that stays inside the threshold without changing cannot repeatedly trigger OR.
- Current stock filters (`in_stock` / `out_of_stock`) always use AND-style filtering; for fixed price thresholds, an already-qualified price alerts when the current stock filter *becomes* satisfied.

## 4. Reliability and examples

- First reliable measurements establish baselines; no alert on the initial observation. Changes to monitoring settings or extraction rule signature rebaseline.
- Unknown stock is neither in nor out of stock. Missing/invalid price is not zero. Missing inputs never invent a stock or price event.
- Detected currency changes block price comparisons until the extractor or currency is corrected. Reliable stock transitions may still notify for an OR rule.
- Reliable prices and stock states are retained independently; no notification is necessary for updating the latest values.
- Do not compare stock quantity fluctuations unless they affect the `in_stock` field.
- No rules selected is invalid. Existing Watch rules from earlier development versions are not migrated.

Examples:

1. **Buy only when in stock below $1300:** `price_mode=below`, `price_threshold=1300`, `stock_mode=in_stock`; qualifying price changes notify by default.
2. **Tell me whenever stock returns:** `price_mode=none`, `stock_mode=restock`.
3. **Any stock or any price movement:** `price_mode=any_change`, `stock_mode=any_change`, `combine_mode=or`.
4. **Only a restock that occurs while price is below $1300:** `price_mode=below`, `price_threshold=1300`, `stock_mode=restock`, `combine_mode=and`.
5. **Restock OR cumulative 10% discount:** `price_mode=percent_down`, `price_threshold=10`, `stock_mode=restock`, `combine_mode=or`.
6. **Price $1280 -> $1350 when below $1300 is selected:** record the price, do not notify; notify on a subsequent valid re-entry below $1300.

The WebUI rule help and its Copy Markdown action use this same document. JSON extraction rules and browser behavior remain separate: see `extractor-rules/AI_RULE_GUIDE.md`.

## 5. Notification templates

Open **Customise notifications** on the Global, Tag, or Watch edit page to choose a preset, save a reusable custom template, or preview the current unsaved title/body. Applying a template copies its title/body/format into the editor but does **not** save; click the normal Save button to activate it. The three presets are General webpage change, Product price and stock, and Compact change alert. Custom templates can be renamed or updated by choosing one and clicking Update, or removed using Delete. Neither operation retroactively changes saved Watch/Tag templates.

**Preview** is read-only and never sends a notification. Global and Tag pages show explicit example data; Watch edit uses the current saved Watch state and latest saved snapshots where available. The result is shown as plain text even if its configured output format is HTML. The actual notification destination may apply additional formatting. Real notification sending uses the existing Apprise pipeline.

The product preset uses `restock.title`, `restock.price`, `restock.currency`, `purchase_alert.stock_text`, `purchase_alert.rule_text`, `purchase_alert.reason_text`, `purchase_alert.reference_price`, `purchase_alert.price_change_amount`, `purchase_alert.percent_change` and `watch_open_url`. Some fields are empty until a qualifying product alert has occurred; the reference price and amount compare against the **triggering event's** saved base, not the display-oriented `restock.last_price`.
