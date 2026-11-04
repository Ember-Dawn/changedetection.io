"""Standalone stock/price policy regressions without Flask dependencies."""
from pathlib import Path
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location('purchase_alert_standalone', Path(__file__).parents[2] / 'changedetectionio/processors/restock_diff/purchase_alert.py')
purchase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purchase)


def item(stock=None, price=None, currency='USD'):
    return {'in_stock': stock, 'price': price, 'currency': currency}


def config(pm='none', sm='restock', threshold=None, follow=True, combine='and'):
    return {'price_mode': pm, 'stock_mode': sm, 'price_threshold': threshold,
            'price_follow_changes': follow, 'combine_mode': combine}


class PurchaseRules(unittest.TestCase):
    def assert_alerts(self, cfg, inputs, expected):
        state = None
        actual = []
        for product in inputs:
            notify, state, _ = purchase.evaluate_purchase_alert(cfg, product, state)
            actual.append(notify)
        self.assertEqual(actual, expected)
        return state

    def test_below_follow_on(self):
        self.assert_alerts(config('below', 'none', 1300),
            [item(True,1400),item(True,1250),item(True,1200),item(True,1280),item(True,1350),item(True,1350),item(True,1290)],
            [False,True,True,True,False,False,True])

    def test_below_follow_off(self):
        self.assert_alerts(config('below','none',1300,False),
            [item(True,1400),item(True,1250),item(True,1200),item(True,1350),item(True,1290)],
            [False,True,False,False,True])

    def test_above(self):
        self.assert_alerts(config('above','none',1500),
            [item(True,1400),item(True,1500),item(True,1550),item(True,1600),item(True,1450),item(True,1520)],
            [False,False,True,True,False,True])

    def test_any_price(self):
        self.assert_alerts(config('any_change','none'),
            [item(None,1000),item(None,900),item(None,900),item(None,1100)],
            [False,True,False,True])

    def test_stock_transitions(self):
        observations = [item(False,100),item(True,100),item(True,100),item(False,100),item(True,100)]
        for sm, expected in [('restock',[False,True,False,False,True]),
                             ('sold_out',[False,False,False,True,False]),
                             ('any_change',[False,True,False,True,True])]:
            with self.subTest(mode=sm):
                self.assert_alerts(config(sm=sm),observations,expected)

    def test_current_stock_filters(self):
        self.assert_alerts(config('below','in_stock',1300),
            [item(False,1250),item(True,1250),item(True,1200),item(False,1200),item(True,1200)],
            [False,True,True,False,True])
        self.assert_alerts(config('above','out_of_stock',1300),
            [item(True,1400),item(False,1400),item(False,1500),item(True,1600)],
            [False,True,True,False])

    def test_and_current_threshold_and_stock_event(self):
        self.assert_alerts(config('below','restock',1300),
            [item(False,1400),item(True,1250),item(True,1150),item(False,1100),item(True,1100)],
            [False,True,False,False,True])
        self.assert_alerts(config('below','restock',1300),
            [item(False,1400),item(True,1400),item(True,1200)],
            [False,False,False])

    def test_or_independent(self):
        self.assert_alerts(config('below','restock',1300,combine='or'),
            [item(False,1400),item(True,1400),item(True,1250),item(False,1220),item(True,1210)],
            [False,True,True,True,True])

    def test_and_any_events(self):
        self.assert_alerts(config('any_change','any_change',combine='and'),
            [item(False,1000),item(True,1000),item(True,900),item(False,800)],
            [False,False,False,True])

    def test_current_stock_filters_percentage_anchor(self):
        self.assert_alerts(config('percent_down','in_stock',10),
            [item(True,1000),item(False,880),item(True,870),item(True,860)],
            [False,False,True,False])
        self.assert_alerts(config('percent_up','out_of_stock',10),
            [item(False,1000),item(True,1120),item(False,1130)],
            [False,False,True])

    def test_cumulative_percentage_modes(self):
        self.assert_alerts(config('percent_down','none',10),
            [item(None,1000),item(None,970),item(None,940),item(None,890),item(None,870),item(None,790)],
            [False,False,False,True,False,True])
        self.assert_alerts(config('percent_up','none',10),
            [item(None,1000),item(None,1050),item(None,1120),item(None,1150)],
            [False,False,True,False])
        self.assert_alerts(config('percent_any','none',10),
            [item(None,1000),item(None,1120),item(None,1050),item(None,990)],
            [False,True,False,True])

    def test_or_stock_event_does_not_reset_percent_anchor(self):
        state = self.assert_alerts(config('percent_down','restock',10,combine='or'),
            [item(False,1000),item(True,970),item(True,890)], [False,True,True])
        self.assertEqual(state['percent_anchor'], '890')

    def test_and_unsent_percent_does_not_reset_anchor(self):
        self.assert_alerts(config('percent_down','restock',10),
            [item(False,1000),item(False,880),item(True,870)], [False,False,True])

    def test_unknown_stock_does_not_trigger_false_events(self):
        self.assert_alerts(config(sm='any_change'),
            [item(False),item(None),item(True),item(None),item(False)],
            [False,False,True,False,True])
        self.assert_alerts(config('below','in_stock',1300),
            [item(True,1400),item(None,1200),item(True,1200)], [False,False,True])

    def test_unknown_stock_preserves_price_event_for_current_stock_filter(self):
        self.assert_alerts(config('below', 'in_stock', 1300),
            [item(True, 1200), item(None, 1100), item(True, 1100)],
            [False, False, True])
        self.assert_alerts(config('any_change', 'in_stock'),
            [item(True, 1200), item(None, 1100), item(True, 1100)],
            [False, False, True])

    def test_partial_missing_data_forces_future_reprocessing(self):
        settings = config('below', 'in_stock', 1300)
        _, state, _ = purchase.evaluate_purchase_alert(settings, item(None, 1400))
        self.assertEqual(state['status'], 'unknown')
        _, state, _ = purchase.evaluate_purchase_alert(settings, item(True, None), state)
        self.assertEqual(state['status'], 'unknown')
        _, state, _ = purchase.evaluate_purchase_alert(settings, item(True, 1200), state)
        self.assertEqual(state['status'], 'ready')

    def test_missing_price_keeps_baseline(self):
        self.assert_alerts(config('any_change','none'),
            [item(True,1000),item(True,None),item(True,900)], [False,False,True])

    def test_currency_conflict_no_price_alert(self):
        settings = config('below','none',1300)
        _, state, _ = purchase.evaluate_purchase_alert(settings,item(True,1400,'USD'))
        notice, state, reason = purchase.evaluate_purchase_alert(settings,item(True,1200,'EUR'),state)
        self.assertFalse(notice)
        self.assertEqual(reason,'currency_changed')
        self.assertEqual(state['last_price'],'1400')
        self.assert_alerts(config('any_change','restock',combine='or'),
            [item(False,1000,'USD'),item(True,900,'EUR')],[False,True])

    def test_policy_and_extraction_reset(self):
        old = config('below','none',1300)
        _, state, _ = purchase.evaluate_purchase_alert(old,item(True,1400))
        notice, state, reason = purchase.evaluate_purchase_alert(config('below','none',1500),item(True,1200),state)
        self.assertFalse(notice)
        self.assertEqual(reason,'baseline')
        notice, _, reason = purchase.evaluate_purchase_alert(config('below','none',1500),item(True,1150),state,reset_baseline=True)
        self.assertFalse(notice)
        self.assertEqual(reason,'baseline')

    def test_invalid_settings(self):
        for cfg in [config('none','none'), config('none','in_stock'),
                    config('below','none'),config('percent_down','none',0),
                    config('percent_down','none',101),config('blah','restock'),
                    config('below','restock',1300,combine='xor')]:
            with self.subTest(cfg=cfg), self.assertRaises(purchase.PurchaseAlertConfigurationError):
                purchase.normalize_settings(cfg)


if __name__ == '__main__':
    unittest.main()
