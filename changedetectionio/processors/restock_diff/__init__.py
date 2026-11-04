
from babel.numbers import parse_decimal
from changedetectionio.model.Watch import model as BaseWatch
from decimal import Decimal, InvalidOperation
from typing import Union
import re

# Processor capabilities
supports_visual_selector = True
supports_browser_steps = True
supports_text_filters_and_triggers = True
supports_text_filters_and_triggers_elements = True
supports_request_type = True
_price_re = re.compile(r"Price:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


class Restock(dict):

    # The one place price text becomes a number - keep it that way, don't strip to [^\d.] and float()
    # at the call site, that turns "39,99" into 3999 (#4493). Used by:
    #   processor.py _deduplicate_prices()                        (itemprop/JSON-LD prices)
    #   pure_python_extractor.py MicrodataExtractor, query_price_availability()
    #   plugins/llm_restock.py get_itemprop_availability_override() (price the LLM returns as a string)
    def parse_currency(self, raw_value: str) -> Union[float, None]:
        # Clean and standardize the value (ie 1,400.00 should be 1400.00), even better would be store the whole thing as an integer.
        standardized_value = raw_value

        if ',' in standardized_value and '.' in standardized_value:
            # Identify the correct decimal separator
            if standardized_value.rfind('.') > standardized_value.rfind(','):
                standardized_value = standardized_value.replace(',', '')
            else:
                standardized_value = standardized_value.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'\D*\d{1,3}(,\d{3})+\D*', standardized_value):
            # Only thousands separators ie "1,299"
            standardized_value = standardized_value.replace(',', '')
        else:
            standardized_value = standardized_value.replace(',', '.')

        # Remove any non-numeric characters except for the decimal point
        standardized_value = re.sub(r'[^\d.-]', '', standardized_value)

        if standardized_value:
            # Convert to float
            # @todo locale needs to be the locale of the webpage
            return float(parse_decimal(standardized_value, locale='en'))

        return None

    def __init__(self, *args, **kwargs):
        # Define default values
        default_values = {
            'in_stock': None,
            'price': None,
            'currency': None,
            'last_price': None  # price at the previous check - drives the % threshold and the watch-list up/down arrow
        }

        # Initialize the dictionary with default values
        super().__init__(default_values)

        # Update with any provided positional arguments (dictionaries)
        if args:
            if len(args) == 1 and isinstance(args[0], dict):
                self.update(args[0])
            else:
                raise ValueError("Only one positional argument of type 'dict' is allowed")

    def __setitem__(self, key, value):
        # Custom logic to handle setting price and last_price
        if key == 'price' or key == 'last_price':
            if isinstance(value, str):
                value = self.parse_currency(raw_value=value)

        super().__setitem__(key, value)

    def get_price_change_percent(self):
        """Signed % change of the current price vs last_price (the previous check's price),
        rounded to one decimal place (e.g. -18.0, 5.3). Returns None when it can't be computed -
        no/zero previous price, non-numeric values, or no change."""
        try:
            price = float(self.get('price'))
            prev = self.get('last_price')
            prev = float(prev) if prev is not None else None
        except (TypeError, ValueError):
            return None

        if prev is None or prev == 0:
            return None

        pct = round((price - prev) / prev * 100.0, 1)
        return pct if pct != 0 else None

# @todo - kinda bad, needs to be in its own DB
def get_price_from_history_str(history_str):
    m = _price_re.search(history_str)
    if not m:
        return None

    try:
        return str(Decimal(m.group(1)))
    except InvalidOperation:
        return None




def _rule_description(state, currency):
    pm = state.get('price_mode') or 'none'
    sm = state.get('stock_mode') or 'none'
    value = state.get('price_threshold')
    unit = (' ' + currency) if currency else ''
    price_map = {
        'none': '', 'below': f'price below {value}{unit}',
        'above': f'price above {value}{unit}', 'any_change': 'any price change',
        'percent_down': f'price down at least {value}%',
        'percent_up': f'price up at least {value}%',
        'percent_any': f'price change at least {value}%',
    }
    stock_map = {
        'none': '', 'in_stock': 'currently in stock',
        'out_of_stock': 'currently out of stock', 'restock': 'restocked',
        'sold_out': 'sold out', 'any_change': 'any stock change',
    }
    price_text, stock_text = price_map.get(pm, ''), stock_map.get(sm, '')
    if price_text and stock_text:
        join = ' AND ' if sm in ('in_stock', 'out_of_stock') or state.get('combine_mode') != 'or' else ' OR '
        return price_text + join + stock_text
    return price_text or stock_text or 'No active rule'


def _reason_description(state):
    reason = state.get('last_alert_reason') or ''
    direction = state.get('last_alert_price_direction')
    pm = state.get('price_mode')
    sm = state.get('stock_mode')
    parts = []
    if 'stock_filter' in reason:
        parts.append('Current stock filter is satisfied')
    elif 'stock' in reason:
        old = state.get('last_alert_previous_stock')
        new = state.get('last_stock')
        if old is False and new is True:
            parts.append('Restocked (out of stock to in stock)')
        elif old is True and new is False:
            parts.append('Sold out (in stock to out of stock)')
        else:
            parts.append('Stock condition met' if sm in ('in_stock', 'out_of_stock') else 'Stock changed')
    if 'price' in reason:
        if pm in ('percent_down', 'percent_up', 'percent_any'):
            parts.append('Cumulative price change reached threshold')
        elif pm in ('below', 'above'):
            parts.append('Price ' + ('rose' if direction == 'up' else 'fell' if direction == 'down' else 'qualified') + ' and meets target')
        else:
            parts.append('Price ' + ('rose' if direction == 'up' else 'fell' if direction == 'down' else 'changed'))
    return '; '.join(parts) or 'Stock/price rule matched'


class Watch(BaseWatch):
    def __init__(self, *arg, **kw):
        super().__init__(*arg, **kw)
        self['restock'] = Restock(kw['default']['restock']) if kw.get('default') and kw['default'].get('restock') else Restock()


    def clear_watch(self):
        super().clear_watch()
        self.update({'restock': Restock()})

    def extra_notification_token_values(self):
        values = super().extra_notification_token_values()
        # Copy so the derived 'previous_price' token added below doesn't mutate the stored restock object
        values['restock'] = dict(self.get('restock', {}))
        state = self.get('purchase_alert_state') or {}
        values['purchase_alert'] = {
            'reason': state.get('last_alert_reason'),
            'price_mode': state.get('price_mode'),
            'stock_mode': state.get('stock_mode'),
            'combine_mode': state.get('combine_mode'),
            'price_threshold': state.get('price_threshold'),
            'percent_change': state.get('last_alert_percent_change'),
            'price_direction': state.get('last_alert_price_direction'),
        }

        stock = values['restock'].get('in_stock')
        alert = values['purchase_alert']
        alert.update({
            'stock_text': 'In stock' if stock is True else 'Out of stock' if stock is False else 'Unknown',
            'stock_previous': state.get('last_alert_previous_stock'),
            'rule_text': _rule_description(state, values['restock'].get('currency') or ''),
            'reason_text': _reason_description(state),
            'reference_price': state.get('last_alert_reference_price'),
            'price_change_amount': state.get('last_alert_price_change_amount'),
        })
        from decimal import Decimal as _D
        currency = str(values['restock'].get('currency') or '').upper()
        symbol = {'USD':'$', 'EUR':'€', 'GBP':'£', 'JPY':'¥', 'CNY':'¥'}.get(currency)
        def money(v):
            try:
                amount = f'{_D(str(v)):,.2f}'
            except (ValueError, InvalidOperation, TypeError):
                return 'Unknown' if v is None else str(v)
            return (symbol or '') + amount + ('' if symbol else (' ' + currency if currency else ''))
        alert['display_price'] = money(values['restock'].get('price'))
        change = state.get('last_alert_price_change_amount')
        if change is not None:
            try:
                delta = _D(str(change))
                direction = '↑ ' if delta > 0 else '↓ ' if delta < 0 else ''
                percent = state.get('last_alert_percent_change')
                alert['display_change'] = direction + money(abs(delta)) + (f' ({percent:+g}%)' if isinstance(percent, (int, float)) else '')
            except (ValueError, InvalidOperation, TypeError):
                alert['display_change'] = ''
        else:
            alert['display_change'] = ''
        values['restock']['previous_price'] = None
        if self.history_n >= 2:
            history = self.history
            if history and len(history) >=2:
                """Unfortunately for now timestamp is stored as string key"""
                # Keys are stored oldest-first (ascending). worker.py saves the new snapshot
                # BEFORE sending the notification, so the newest key ([-1]) is the current check
                # and the previous check is the second-newest ([-2]). Guaranteed to exist here
                # because len(history) >= 2.
                sorted_keys = sorted(list(history), key=lambda x: int(x))

                price_str = self.get_history_snapshot(timestamp=sorted_keys[-2])
                if price_str:
                    values['restock']['previous_price'] = get_price_from_history_str(price_str)
        return values

    def extra_notification_token_placeholder_info(self):
        values = super().extra_notification_token_placeholder_info()

        values.append(('restock.stock_quantity', "Optional stock quantity extracted by custom rule"))
        values.append(('restock.sku', "Optional SKU extracted by custom rule"))
        values.append(('restock.title', "Optional product title extracted by custom rule"))
        values.append(('restock.price', "Price detected"))
        values.append(('restock.in_stock', "In stock status"))
        values.append(('restock.last_price', "Price at the previous check"))
        values.append(('restock.previous_price', "Previous price in history"))
        values.append(('purchase_alert.reason', "Reason(s) for the latest stock/price alert"))
        values.append(('purchase_alert.price_mode', "Configured price monitoring mode"))
        values.append(('purchase_alert.stock_mode', "Configured stock monitoring mode"))
        values.append(('purchase_alert.combine_mode', "Configured stock/price combination"))
        values.append(('purchase_alert.price_threshold', "Configured price or percentage threshold"))
        values.append(('purchase_alert.percent_change', "Percent change on the latest stock/price alert"))
        values.append(('purchase_alert.reason_text', 'Human-readable reason for latest stock/price alert'))
        values.append(('purchase_alert.rule_text', 'Human-readable active stock/price rule'))
        values.append(('purchase_alert.stock_text', 'In stock / Out of stock / Unknown'))
        values.append(('purchase_alert.stock_previous', 'Previous reliable stock state at alert'))
        values.append(('purchase_alert.reference_price', 'Price reference used for the alert'))
        values.append(('purchase_alert.price_change_amount', 'Signed price change since reference'))
        values.append(('purchase_alert.price_direction', "Price movement direction on latest alert"))

        return values

