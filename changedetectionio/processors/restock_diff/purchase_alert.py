"""Purchase-oriented notification decision, independent of the HTML extractor.

The first valid check (and an edited policy) establishes a baseline.  A qualified
product notifies when entering qualification, or when its price changes while
qualified; stock-only monitoring notifies only on entering in-stock.

An unknown input never turns a previously known state into a false one.  All
persistent state is JSON-compatible and stored on the existing Watch object.
"""

from decimal import Decimal, InvalidOperation
import hashlib
import json


MODES = ('stock_and_price', 'stock_only', 'price_only')


class PurchaseAlertConfigurationError(ValueError):
    pass


def _price(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        return None
    try:
        value = Decimal(str(value))
        return value if value.is_finite() and value >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalize_settings(settings):
    mode = settings.get('alert_mode') or 'stock_only'
    if mode not in MODES:
        raise PurchaseAlertConfigurationError('Invalid product alert mode')
    target = _price(settings.get('target_price')) if mode != 'stock_only' else None
    if mode != 'stock_only' and target is None:
        raise PurchaseAlertConfigurationError('Set a valid non-negative target price for price monitoring')
    return mode, target


def _fingerprint(mode, target):
    # Configuration changes start a new baseline, not a fictional price event.
    payload = json.dumps({'v': 1, 'mode': mode,
                          'target': str(target.normalize()) if target is not None else None},
                         sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def evaluate_purchase_alert(settings, product, previous_state=None, reset_baseline=False):
    """Return (notify: bool, state: dict, reason: str).

    `product` is a dict containing `in_stock`, `price` and optional `currency`.
    `previous_state` comes from the last successful evaluation, not the last
    snapshot.  Unknown evaluations retain known qualification/price.
    """
    mode, target = normalize_settings(settings)
    signature = _fingerprint(mode, target)
    stock = product.get('in_stock')
    if stock is not True and stock is not False:
        stock = None
    price = _price(product.get('price'))
    currency = (str(product.get('currency') or '').upper().strip() or None)

    if mode == 'stock_only':
        qualified = stock
    elif mode == 'price_only':
        qualified = None if price is None else price < target
    elif stock is False or (price is not None and price >= target):
        qualified = False
    elif stock is True and price is not None:
        qualified = True
    else:
        qualified = None

    prior = previous_state if isinstance(previous_state, dict) else {}
    same_policy = prior.get('signature') == signature and not reset_baseline
    if not same_policy:
        prior = {}

    # Comparing a USD target against a EUR extraction is not meaningful.
    # Do not trigger a price event across a detected currency transition;
    # require an operator to correct the rule/watch configuration first.
    previous_currency = prior.get('reference_currency')
    currency_conflict = (mode != 'stock_only' and previous_currency and currency
                         and previous_currency != currency)
    result = dict(prior)
    result['signature'] = signature
    result['mode'] = mode
    result['target_price'] = str(target) if target is not None else None
    result['status'] = ('qualified' if qualified is True else
                        'unqualified' if qualified is False else 'unknown')
    if qualified is None or currency_conflict:
        # Do not overwrite the last reliable state on partial/captcha pages,
        # or when the same watch unexpectedly switches price currency.
        reason = 'currency_changed' if currency_conflict else 'unknown'
        result['status'] = 'unknown'
        result['last_reason'] = reason
        return False, result, reason

    old_qualified = prior.get('qualified')
    old_price = _price(prior.get('last_qualified_price'))
    # A saved state with qualified=None is still a baseline from an unknown
    # check; do not notify until the first valid state is established.
    baseline = not same_policy or 'qualified' not in prior
    notify = False
    reason = 'unchanged'
    if baseline:
        reason = 'baseline'
    elif qualified is True:
        if old_qualified is False:
            notify, reason = True, 'became_qualified'
        elif old_qualified is True and mode != 'stock_only' and price is not None and old_price is not None and price != old_price:
            notify, reason = True, 'price_changed'

    result['qualified'] = qualified
    if currency and mode != 'stock_only':
        result['reference_currency'] = currency
    if qualified and mode != 'stock_only' and price is not None:
        result['last_qualified_price'] = str(price)
        result['last_qualified_currency'] = currency
    elif not qualified:
        result['last_qualified_price'] = None
        result['last_qualified_currency'] = None

    if notify:
        result['last_alert_reason'] = reason
        result['last_alert_price'] = str(price) if price is not None else None
    result['last_reason'] = reason
    return notify, result, reason
