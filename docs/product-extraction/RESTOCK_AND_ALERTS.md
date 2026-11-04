# Restock & Price monitoring

**Source of truth:** [STOCK_PRICE_RULES.md](STOCK_PRICE_RULES.md). This document describes integration with the existing changedetection.io fork.

The Watch's **Stock & Price** settings now choose a price mode first and then a stock mode. If both price and a stock *event* mode are enabled, AND is the default and OR is optional. Current in-stock/out-of-stock modes are only price filters. A fixed-price rule continues to notify of any price change within its qualified range by default; this is configurable.

The rule evaluator is `changedetectionio/processors/restock_diff/purchase_alert.py`, invoked from `processor.py` after extraction. It uses the existing persisted Watch `purchase_alert_state` without a new database. The first successful relevant observation and changes to settings or extraction-rule signature create a new baseline. Failed or unknown extraction values do not become false in-stock or out-of-stock events. Price comparison and percentage anchors remain separate from the display-oriented `restock.last_price` value.

### Editing and API

The Watch/Tag editor exposes the configuration fields `price_mode`, `price_threshold`, `price_follow_changes`, `stock_mode`, `combine_mode`, `extraction_mode`, `extraction_rule_id`. The form contains a collapsed **Monitoring rules** panel and **Copy Markdown** action; the text comes directly from `STOCK_PRICE_RULES.md`. The same configuration is documented in `changedetectionio/processors/restock_diff/api.yaml`. A Group tag with `overrides_watch` still overrides Watch settings.

Available notification tokens include `purchase_alert.reason`, `purchase_alert.price_mode`, `purchase_alert.stock_mode`, `purchase_alert.combine_mode`, `purchase_alert.price_threshold`, `purchase_alert.percent_change`, `purchase_alert.price_direction`, plus the existing `restock.price` and `restock.in_stock` values. Normal Worker and Apprise scheduling/notification reliability is unchanged; a rule decision does not guarantee external delivery. Product Extractors Dry Run remains read-only.

### Run checks

Run `python -m unittest discover -s tests/product_extraction -p 'test_purchase*.py'` and related extraction tests. Run UI/Docker/CloakBrowser/real-retailer and notification delivery checks in the deployment environment. No old `alert_mode` or `target_price` migration is provided; reconfigure existing development Watches after applying the patch.
