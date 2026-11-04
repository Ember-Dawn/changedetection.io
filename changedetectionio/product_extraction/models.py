"""Validated, deterministic product extraction results (not watch history)."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re


class RuleError(ValueError):
    pass


@dataclass
class ProductData:
    price: Decimal | None = None
    currency: str | None = None
    in_stock: bool | None = None
    stock_quantity: int | None = None
    title: str | None = None
    sku: str | None = None
    rule_id: str | None = None
    field_details: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            'price': str(self.price) if self.price is not None else None,
            'currency': self.currency, 'in_stock': self.in_stock,
            'stock_quantity': self.stock_quantity, 'title': self.title,
            'sku': self.sku, 'rule_id': self.rule_id,
        }


def money(value):
    if isinstance(value, bool) or value is None:
        raise RuleError('Missing product price')
    raw = re.sub(r'[^0-9.,-]', '', str(value).strip())
    if not raw:
        raise RuleError('Price has no digits')
    if ',' in raw and '.' in raw:
        if raw.rfind(',') > raw.rfind('.'):
            raw = raw.replace('.', '').replace(',', '.')
        else:
            raw = raw.replace(',', '')
    elif ',' in raw:
        raw = raw.replace(',', '') if re.fullmatch(r'\d{1,3}(,\d{3})+', raw) else raw.replace(',', '.')
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount < 0:
            raise RuleError('Price is not a finite positive amount')
        return amount
    except InvalidOperation as exc:
        raise RuleError('Invalid product price') from exc
