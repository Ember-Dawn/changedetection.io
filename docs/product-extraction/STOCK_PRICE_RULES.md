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

- First reliable measurements establish baselines; no alert on the initial observation. Changes to monitoring settings or semantic extraction fields may rebaseline; changes only to rule name, URL match patterns, or `page.extra_wait_seconds` do not.
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

The policy rules above determine **when to notify**, not how to render a message. Six current built-ins cover general changes, product Plain Text, compact changes, Telegram HTML (compact / all details), and Telegram Rich (all details). Compatible newly created product Watches use HTML Compact by default when all effective destinations are Telegram and no notification fields are supplied. Selecting a template changes Format immediately; **Apply to editor** copies Title and Body; the normal Save is still necessary. Existing Watches do not automatically inherit library edits.

See [NOTIFICATION_TEMPLATES.md](NOTIFICATION_TEMPLATES.md) for templates, Chinese names, dialogs, dynamic display fields and links. See [RESTOCK_AND_ALERTS.md](RESTOCK_AND_ALERTS.md) for notification event evaluation and dispatch.

## 5. Rule selection, fetch wait and rule errors

- For new Stock & Price alerts Watches, the editor suggests the single enabled JSON rule matching the URL using `match.domains` and `match.path_patterns`. Existing Watch selections are left untouched. If there are zero or multiple matches, choose manually.
- Select **Selected rule only** to require the chosen JSON rule; **Built-in** uses metadata/plugins. Legacy stored `auto` configurations remain readable, but Auto is not offered for new configurations.
- An optional JSON property `"page": {"extra_wait_seconds": 5}` adds 5 seconds after browser navigation. Integer range: 0–30. Wait precedence: explicitly configured Watch delay (including 0) > JSON rule > global delay > fetcher default. Non-browser fetchers ignore rendering delays.
- A selected rule with missing/invalid required price or stock status is a failure, not a false out-of-stock event. The first rule error queues a notification; continued failures are quiet after successful delivery; recovery queues one notification. Failed delivery is retried on later checks, subject to a short retry interval. These operational notices use the configured destination and are independent of user-facing price/stock templates.
- A solely changed waiting time does not rebaseline price/stock history. The first check after upgrading old full-JSON signatures adopts extraction-only signatures without a forced baseline reset.
