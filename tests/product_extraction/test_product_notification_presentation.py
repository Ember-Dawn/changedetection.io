"""Dependency-free product notification presentation tests."""
import ast
from decimal import Decimal, InvalidOperation
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BaseWatch(dict):
    history_n = 0
    def extra_notification_token_values(self):
        return {}


def load_watch():
    tree = ast.parse((ROOT / 'changedetectionio/processors/restock_diff/__init__.py').read_text(encoding='utf8'))
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in ('_rule_description', '_reason_description')]
    watch = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Watch')
    method = next(n for n in watch.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'extra_notification_token_values')
    classnode = ast.ClassDef(name='Watch', bases=[ast.Name(id='BaseWatch', ctx=ast.Load())],
                             keywords=[], body=[method], decorator_list=[])
    ns = {'BaseWatch':BaseWatch, 'Decimal':Decimal, 'InvalidOperation':InvalidOperation}
    source = ast.fix_missing_locations(ast.Module(body=[*helpers, classnode], type_ignores=[]))
    exec(compile(source, '<notification presentation>', 'exec'), ns)
    return ns['Watch']


class ProductPresentationTest(unittest.TestCase):
    def setUp(self):
        self.Watch = load_watch()

    def tokens(self, state, price=890, stock=True):
        return self.Watch({'purchase_alert_state':state,
                           'restock':{'price':price,'currency':'USD','in_stock':stock}}
                          ).extra_notification_token_values()['purchase_alert']

    def test_percentage_uses_cumulative_anchor_and_amount(self):
        data=self.tokens(dict(price_mode='percent_down', stock_mode='none',
                              price_threshold='10', last_alert_reason='price',
                              last_alert_reference_price='1000',
                              last_alert_price_change_amount='-110',
                              last_alert_percent_change='-11'))
        self.assertEqual(data['display_price'], '$890.00')
        self.assertEqual(data['display_change'], '(−11%, ↓ $110.00)')
        self.assertTrue(data['show_price'])
        self.assertFalse(data['show_stock'])

    def test_stock_only_and_event_labels(self):
        data=self.tokens(dict(price_mode='none',stock_mode='restock',
                              last_alert_reason='stock',
                              last_alert_previous_stock=False),1250,True)
        self.assertFalse(data['show_price'])
        self.assertEqual(data['display_stock'], '✅ Restocked')
        self.assertTrue(data['show_stock'])
        self.assertEqual(data['display_change'], '')

    def test_or_stock_trigger_shows_nonqualifying_price_without_claiming_price_trigger(self):
        data=self.tokens(dict(price_mode='percent_down',stock_mode='restock',
                              combine_mode='or',price_threshold='10',
                              last_alert_reason='stock',last_alert_previous_stock=False,
                              last_alert_reference_price='1000',
                              last_alert_price_change_amount='-30'),970,True)
        self.assertEqual(data['display_change'], '(−3%, ↓ $30.00)')
        self.assertEqual(data['display_stock'], '✅ Restocked')
        self.assertNotIn('Cumulative',data['reason_text'])

    def test_missing_values_are_hidden(self):
        data=self.tokens(dict(price_mode='below',stock_mode='in_stock',
                              last_alert_reason=''),None,None)
        self.assertFalse(data['show_price'])
        self.assertFalse(data['show_stock'])
        self.assertEqual(data['display_stock'], '')

    def test_fixed_target_rise_format(self):
        data=self.tokens(dict(price_mode='below',stock_mode='in_stock',
                              last_alert_reason='price+stock_filter',
                              last_alert_reference_price='1200',
                              last_alert_price_change_amount='80'),1280,True)
        self.assertEqual(data['display_change'], '(+6.67%, ↑ $80.00)')
        self.assertEqual(data['display_stock'], '✅ In stock')


if __name__ == '__main__':
    unittest.main()
