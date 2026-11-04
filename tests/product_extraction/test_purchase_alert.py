"""Pure purchase-policy regression tests; no Flask or browser required."""
import importlib.util
from pathlib import Path
import unittest

module_path = Path(__file__).parents[2] / 'changedetectionio/processors/restock_diff/purchase_alert.py'
spec = importlib.util.spec_from_file_location('purchase_alert_standalone', module_path)
purchase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purchase)


def item(stock, price=None, currency='USD'):
    return {'in_stock': stock, 'price': price, 'currency': currency}


class PurchaseAlerts(unittest.TestCase):
    def check_series(self, config, cases):
        state = None
        for current, expected, expected_reason in cases:
            notified, state, reason = purchase.evaluate_purchase_alert(config, current, state)
            self.assertEqual(notified, expected, (current, reason))
            self.assertEqual(reason, expected_reason, current)

    def test_stock_and_price_price_moves_both_directions(self):
        self.check_series({'alert_mode':'stock_and_price','target_price':1300}, [
            (item(True,1250),False,'baseline'),
            (item(True,1250),False,'unchanged'),
            (item(True,1100),True,'price_changed'),
            (item(True,1200),True,'price_changed'),
            (item(True,1200),False,'unchanged'),
            (item(True,1350),False,'unchanged'),
            (item(True,1250),True,'became_qualified'),
            (item(False,1100),False,'unchanged'),
            (item(True,1100),True,'became_qualified'),
        ])

    def test_first_check_does_not_notify(self):
        for mode in purchase.MODES:
            settings={'alert_mode':mode,'target_price':1300}
            result, state, reason=purchase.evaluate_purchase_alert(settings,item(True,1200))
            self.assertFalse(result)
            self.assertEqual(reason,'baseline')
            self.assertTrue(state['qualified'])

    def test_strict_boundary(self):
        self.check_series({'alert_mode':'stock_and_price','target_price':1300}, [
            (item(True,1300),False,'baseline'),
            (item(True,1299.99),True,'became_qualified'),
            (item(True,1300),False,'unchanged'),
            (item(True,1299.99),True,'became_qualified'),
        ])

    def test_stock_only(self):
        self.check_series({'alert_mode':'stock_only'}, [
            (item(False, 1400),False,'baseline'),
            (item(True, 1400),True,'became_qualified'),
            (item(True, 1100),False,'unchanged'),
            (item(None,1100),False,'unknown'),
            (item(True, 1200),False,'unchanged'),
            (item(False,1200),False,'unchanged'),
            (item(True, 1200),True,'became_qualified'),
        ])

    def test_price_only(self):
        self.check_series({'alert_mode':'price_only','target_price':1300}, [
            (item(False,1450),False,'baseline'),
            (item(False,1250),True,'became_qualified'),
            (item(None,1200),True,'price_changed'),
            (item(True,1200),False,'unchanged'),
        ])

    def test_unknown_keeps_previous_qualified_and_price(self):
        config={'alert_mode':'stock_and_price','target_price':1300}
        _, state, _=purchase.evaluate_purchase_alert(config,item(True,1250))
        notified,state,reason=purchase.evaluate_purchase_alert(config,item(None,1100),state)
        self.assertFalse(notified)
        self.assertEqual(reason,'unknown')
        self.assertTrue(state['qualified'])
        self.assertEqual(state['last_qualified_price'],'1250')
        notified,state,reason=purchase.evaluate_purchase_alert(config,item(True,None),state)
        self.assertFalse(notified)
        self.assertEqual(reason,'unknown')
        notified,state,reason=purchase.evaluate_purchase_alert(config,item(True,1100),state)
        self.assertTrue(notified)
        self.assertEqual(reason,'price_changed')

    def test_known_false_even_when_other_field_missing(self):
        settings={'alert_mode':'stock_and_price','target_price':1300}
        _,state,_=purchase.evaluate_purchase_alert(settings,item(True,1100))
        _,state,reason=purchase.evaluate_purchase_alert(settings,item(False,None),state)
        self.assertEqual(state['qualified'],False)
        self.assertEqual(state['status'],'unqualified')
        self.assertEqual(reason,'unchanged')
        _,state,reason=purchase.evaluate_purchase_alert(settings,item(True,1100),state)
        self.assertEqual(reason,'became_qualified')

    def test_policy_change_resets_baseline(self):
        old={'alert_mode':'stock_and_price','target_price':1300}
        _,state,_=purchase.evaluate_purchase_alert(old,item(True,1200))
        notified,state,reason=purchase.evaluate_purchase_alert(
            {'alert_mode':'stock_and_price','target_price':1400},item(True,1100),state)
        self.assertFalse(notified)
        self.assertEqual(reason,'baseline')

    def test_rule_change_resets_baseline(self):
        s={'alert_mode':'stock_and_price','target_price':1300}
        _,state,_=purchase.evaluate_purchase_alert(s,item(True,1200))
        notified,_,reason=purchase.evaluate_purchase_alert(s,item(True,1100),state,reset_baseline=True)
        self.assertFalse(notified)
        self.assertEqual(reason,'baseline')

    def test_currency_change_never_generates_false_price_event(self):
        settings={'alert_mode':'stock_and_price','target_price':1300}
        _,state,_=purchase.evaluate_purchase_alert(settings,item(True,1250,'USD'))
        notify,state,reason=purchase.evaluate_purchase_alert(settings,item(True,1200,'EUR'),state)
        self.assertFalse(notify)
        self.assertEqual(reason,'currency_changed')
        self.assertEqual(state['last_qualified_currency'],'USD')
        self.assertEqual(state['last_qualified_price'],'1250')

    def test_invalid_price_and_configuration(self):
        config={'alert_mode':'stock_and_price','target_price':1300}
        for price in (None, '', 'NaN','Infinity',-100,True):
            result,state,reason=purchase.evaluate_purchase_alert(config,item(True,price))
            self.assertFalse(result)
            self.assertEqual(reason,'unknown')
        for invalid in ({'alert_mode':'price_only'}, {'alert_mode':'stock_and_price','target_price':'foo'}, {'alert_mode':'not_valid'}):
            with self.assertRaises(purchase.PurchaseAlertConfigurationError):
                purchase.evaluate_purchase_alert(invalid,item(True,1100))


if __name__ == '__main__':
    unittest.main()
