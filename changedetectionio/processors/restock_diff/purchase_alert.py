"""Independent stock and price events for one product Watch.

A policy change and the first reliable observation establish baselines without
alerts. Unknown fields never masquerade as stock/price changes. The percentage
anchor advances only when a percentage event participates in an actual alert.
"""

from decimal import Decimal, InvalidOperation
import hashlib
import json

PRICE_MODES = ('none', 'below', 'above', 'any_change', 'percent_down', 'percent_up', 'percent_any')
STOCK_MODES = ('none', 'in_stock', 'out_of_stock', 'restock', 'sold_out', 'any_change')
STOCK_EVENTS = ('restock', 'sold_out', 'any_change')
PERCENT_MODES = ('percent_down', 'percent_up', 'percent_any')


class PurchaseAlertConfigurationError(ValueError):
    pass


def _price(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalize_settings(settings):
    settings = settings or {}
    price_mode = settings.get('price_mode') or 'none'
    stock_mode = settings.get('stock_mode') or 'none'
    combine_mode = settings.get('combine_mode') or 'and'
    follow = settings.get('price_follow_changes', True)
    if price_mode not in PRICE_MODES or stock_mode not in STOCK_MODES:
        raise PurchaseAlertConfigurationError('Invalid stock or price monitoring mode')
    if combine_mode not in ('and', 'or'):
        raise PurchaseAlertConfigurationError('Invalid stock/price combination')
    if price_mode == 'none' and stock_mode == 'none':
        raise PurchaseAlertConfigurationError('Enable at least one stock or price rule')
    if price_mode == 'none' and stock_mode in ('in_stock', 'out_of_stock'):
        raise PurchaseAlertConfigurationError('Current stock filters require price monitoring')
    if stock_mode in ('in_stock', 'out_of_stock') and combine_mode == 'or':
        raise PurchaseAlertConfigurationError('Current stock filters always use AND with price')
    threshold = _price(settings.get('price_threshold')) if price_mode not in ('none', 'any_change') else None
    if price_mode not in ('none', 'any_change') and threshold is None:
        raise PurchaseAlertConfigurationError('A non-negative price/percentage threshold is required')
    if price_mode in PERCENT_MODES and (threshold <= 0 or (price_mode == 'percent_down' and threshold > 100)):
        raise PurchaseAlertConfigurationError('Percentage must be positive; a decrease cannot exceed 100%')
    if not isinstance(follow, bool):
        raise PurchaseAlertConfigurationError('price_follow_changes must be boolean')
    return price_mode, stock_mode, combine_mode, threshold, follow


def _fingerprint(config):
    price_mode, stock_mode, combine, threshold, follow = config
    data = (2, price_mode, stock_mode, combine, str(threshold) if threshold is not None else None, follow)
    return hashlib.sha256(json.dumps(data, separators=(',', ':')).encode('utf-8')).hexdigest()


def _stock_event(mode, previous, stock):
    if stock is None or previous is None or previous == stock:
        return False
    return ((mode == 'restock' and stock is True) or
            (mode == 'sold_out' and stock is False) or
            mode == 'any_change')


def _percent_event(mode, base, current, threshold):
    if base is None or current is None or base <= 0:
        return False
    delta = (current - base) * 100 / base
    return ((mode == 'percent_up' and delta >= threshold) or
            (mode == 'percent_down' and delta <= -threshold) or
            (mode == 'percent_any' and abs(delta) >= threshold))


def policy_signature(settings):
    """Hash the active policy so unchanged HTML cannot hide Tag policy edits."""
    return _fingerprint(normalize_settings(settings))


def evaluate_purchase_alert(settings, product, previous_state=None, reset_baseline=False):
    """Return (notify, json_compatible_state, reason).

    For AND + stock event + price threshold, price is a current condition,
    not an event. Other price modes require a price event in the same check.
    Stock current-state filters always gate the price branch (never OR).
    """
    config = normalize_settings(settings)
    pm, sm, combine, threshold, follow = config
    signature = _fingerprint(config)
    prior = previous_state if isinstance(previous_state, dict) else {}
    if reset_baseline or prior.get('signature') != signature:
        prior = {}

    stock = product.get('in_stock')
    stock = stock if stock is True or stock is False else None
    price = _price(product.get('price'))
    currency = (str(product.get('currency') or '').strip().upper() or None)
    old_currency = prior.get('reference_currency')
    conflict = bool(pm != 'none' and price is not None and currency and old_currency and currency != old_currency)
    old_stock = prior.get('last_stock') if prior.get('last_stock') in (True, False) else None
    old_price = _price(prior.get('last_price'))
    anchor = _price(prior.get('percent_anchor'))
    stock_first = sm != 'none' and old_stock is None
    price_first = pm != 'none' and old_price is None
    stock_event = _stock_event(sm, old_stock, stock)
    current_filter = sm in ('in_stock', 'out_of_stock')
    stock_matches = stock is (sm == 'in_stock') if current_filter else stock_event

    price_qualified = False
    price_event = False
    if pm != 'none' and price is not None and not conflict:
        if pm in ('below', 'above'):
            price_qualified = price < threshold if pm == 'below' else price > threshold
            was_qualified = (old_price < threshold if pm == 'below' else old_price > threshold) if old_price is not None else False
            price_event = bool(not price_first and price_qualified and
                               (not was_qualified or (follow and price != old_price)))
        elif pm == 'any_change':
            price_qualified = price_event = bool(not price_first and price != old_price)
        else:
            price_event = _percent_event(pm, anchor, price, threshold)
            price_qualified = price_event

    # For current-stock filters, a newly satisfied stock state can make an
    # already-qualified fixed-price rule actionable even when price is stable.
    if current_filter and pm in ('below', 'above') and price_qualified:
        # A price change during unknown stock must not consume the future
        # qualified transition once stock becomes known again.
        price_event = price_event or (stock_matches and prior.get('filter_qualified') is False)

    # Avoid spurious first alerts when either required branch is only now
    # acquiring its first reliable observation.
    if sm == 'none':
        candidate = price_event
        causes = ['price'] if candidate else []
    elif pm == 'none':
        candidate = stock_event
        causes = ['stock'] if candidate else []
    elif current_filter:
        candidate = bool(stock_matches and price_event)
        causes = ['price', 'stock_filter'] if candidate else []
    elif combine == 'or':
        candidate = bool(stock_event or price_event)
        causes = (['stock'] if stock_event else []) + (['price'] if price_event else [])
    else:
        # Fixed threshold is a state, while other price rules are events.
        price_side = price_qualified if pm in ('below', 'above') else price_event
        candidate = bool(stock_event and price_side)
        causes = ['stock', 'price'] if candidate else []

    # Initial acquisition of a required state cannot count as an event.
    if sm != 'none' and pm == 'none' and stock_first:
        candidate = False
    if current_filter and (stock_first or price_first):
        candidate = False
    if pm != 'none' and sm == 'none' and price_first:
        candidate = False
    if pm != 'none' and sm in STOCK_EVENTS and combine == 'and' and pm in ('below', 'above') and price_first:
        candidate = False
    if conflict and combine != 'or':
        candidate = False
    if conflict and combine == 'or':
        candidate = stock_event
        causes = ['stock'] if candidate else []
    if not candidate:
        causes = []

    result = dict(prior)
    result.update(signature=signature, price_mode=pm, stock_mode=sm,
                  combine_mode=combine, price_threshold=str(threshold) if threshold is not None else None,
                  status='unknown' if (conflict or (pm != 'none' and price is None) or
                                       (sm != 'none' and stock is None)) else 'ready')
    if stock is not None:
        result['last_stock'] = stock
    if current_filter and pm in ('below', 'above') and not conflict:
        if stock is not None and price is not None:
            result['filter_qualified'] = bool(stock_matches and price_qualified)
        elif stock is not None and not stock_matches:
            result['filter_qualified'] = False
    if pm != 'none' and price is not None and not conflict and not (current_filter and stock is None):
        result['last_price'] = str(price)
        if currency:
            result['reference_currency'] = currency
        if pm in PERCENT_MODES and anchor is None and price > 0:
            result['percent_anchor'] = str(price)
        if candidate and 'price' in causes and pm in PERCENT_MODES and price > 0:
            result['percent_anchor'] = str(price)
    if candidate:
        reason = '+'.join(causes)
        change_base = anchor if pm in PERCENT_MODES else old_price
        if price is not None and change_base is not None and change_base > 0 and not conflict:
            result['last_alert_percent_change'] = str((price - change_base) * 100 / change_base)
            result['last_alert_price_direction'] = ('up' if price > change_base else
                                                    'down' if price < change_base else 'unchanged')
        else:
            result['last_alert_percent_change'] = None
            result['last_alert_price_direction'] = None
        result['last_alert_reason'] = reason
        result['last_alert_price'] = str(price) if price is not None else None
    elif conflict:
        reason = 'currency_changed'
    elif (stock_first and sm != 'none') or (price_first and pm != 'none'):
        reason = 'baseline'
    else:
        reason = 'unchanged'
    result['last_reason'] = reason
    return bool(candidate), result, reason
