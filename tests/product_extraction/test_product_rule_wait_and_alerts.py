"""Regression contracts for per-rule waits and delivery-aware operational alerts."""
import copy
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from changedetectionio.product_extraction.registry import (
    validate, signature, extraction_signature, matches, matching_rules, save,
)
from changedetectionio.product_extraction.models import RuleError
from changedetectionio import product_rule_alerts


class FakeWatch(dict):
    @property
    def open_link_override(self):
        return ''


class FakeStore:
    def __init__(self, watch):
        self.data = {'watching': {'w1': watch}}
        self.events = []

    def update_watch(self, uuid, update_obj):
        self.data['watching'][uuid].update(update_obj)
        self.events.append(copy.deepcopy(update_obj))


class ProductWaitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rule = {
            'schema_version': 1, 'id': 'store-a', 'name': 'Store A',
            'enabled': True, 'match': {'domains': ['example.com'], 'path_patterns': ['/product/*']},
            'fields': {'price': {'type': 'css', 'value': '.price'}},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_optional_wait_validation(self):
        self.assertEqual(validate(self.rule), self.rule)
        for valid in (0, 5, 30):
            rule = copy.deepcopy(self.rule)
            rule['page'] = {'extra_wait_seconds': valid}
            self.assertEqual(validate(rule)['page']['extra_wait_seconds'], valid)
        for invalid in (-1, 31, 1.5, True, '5'):
            rule = copy.deepcopy(self.rule)
            rule['page'] = {'extra_wait_seconds': invalid}
            with self.assertRaises(RuleError):
                validate(rule)
        with self.assertRaises(RuleError):
            validate({**self.rule, 'page': {'unsupported': 2}})

    def test_wait_or_name_change_preserves_extraction_signature(self):
        rule = copy.deepcopy(self.rule)
        rule['page'] = {'extra_wait_seconds': 8}
        rule['name'] = 'Renamed'
        self.assertNotEqual(signature(rule), signature(self.rule))
        self.assertEqual(extraction_signature(rule), extraction_signature(self.rule))
        rule['fields']['price']['value'] = '#price'
        self.assertNotEqual(extraction_signature(rule), extraction_signature(self.rule))

    def test_matching_uses_registry_url_semantics(self):
        with patch.dict('os.environ', {'PRODUCT_EXTRACTOR_RULES_DIR': self.temp.name}):
            save(self.rule)
            selected = matching_rules('https://www.example.com/product/123')
            self.assertEqual([r['id'] for r in selected], ['store-a'])
            self.assertEqual(matching_rules('https://fakeexample.com/product/123'), [])
            self.assertEqual(matching_rules('https://example.com/not-product'), [])


class ProductAlertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, 'restock_diff.json').write_text(json.dumps({'restock_diff': {
            'extraction_rule_id': 'bestbuy-products',
        }}))
        self.watch = FakeWatch({
            'processor': 'restock_diff', 'url': 'https://example.com/product/123',
            'title': 'A <GPU> & accessories', 'notification_urls': ['tgram://token/chat'],
            'product_rule_alert_state': {}, 'notification_muted': False,
        })
        self.watch.data_dir = self.tmp.name
        self.store = FakeStore(self.watch)
        self.q = queue.Queue()
        self.now = 10000.0
        # Suppress transport setup and use the same context structure.
        self.patches = [
            patch('changedetectionio.notification_service._check_cascading_vars',
                  side_effect=lambda datastore, field, watch: watch['notification_urls']),
            patch.object(product_rule_alerts.time, 'time', return_value=self.now),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_first_failure_only_once_until_recovery(self):
        product_rule_alerts.failure(self.store, self.q, 'w1', 'Price missing')
        first = self.q.get_nowait()
        self.assertEqual(first['notification_format'], 'telegram_html')
        self.assertIn('<a href="https://example.com/product/123">A &lt;GPU&gt; &amp; accessories</a>', first['notification_body'])
        self.assertEqual(first['product_rule_event'], 'failure')
        self.assertTrue(product_rule_alerts.delivery_is_current(self.store, first))
        product_rule_alerts.acknowledge(self.store, first, succeeded=True)
        product_rule_alerts.failure(self.store, self.q, 'w1', 'Still missing')
        self.assertTrue(self.q.empty())
        product_rule_alerts.recovered(self.store, self.q, 'w1')
        recovery = self.q.get_nowait()
        self.assertEqual(recovery['product_rule_event'], 'recovery')
        product_rule_alerts.acknowledge(self.store, recovery, succeeded=True)
        self.assertFalse(self.watch['product_rule_alert_state'])
        product_rule_alerts.failure(self.store, self.q, 'w1', 'Missing again')
        self.assertEqual(self.q.get_nowait()['product_rule_event'], 'failure')

    def test_delivery_failure_retries_after_cooldown(self):
        product_rule_alerts.failure(self.store, self.q, 'w1', 'No price')
        first = self.q.get_nowait()
        product_rule_alerts.acknowledge(self.store, first, succeeded=False)
        product_rule_alerts.failure(self.store, self.q, 'w1', 'No price')
        self.assertTrue(self.q.empty())
        with patch.object(product_rule_alerts.time, 'time', return_value=self.now + 301):
            product_rule_alerts.failure(self.store, self.q, 'w1', 'No price')
        retry = self.q.get_nowait()
        self.assertNotEqual(retry['product_rule_token'], first['product_rule_token'])

    def test_recovery_before_failure_delivery_skips_notice(self):
        product_rule_alerts.failure(self.store, self.q, 'w1', 'No stock')
        first = self.q.get_nowait()
        product_rule_alerts.recovered(self.store, self.q, 'w1')
        self.assertFalse(product_rule_alerts.delivery_is_current(self.store, first))
        self.assertFalse(self.watch['product_rule_alert_state'])
        self.assertTrue(self.q.empty())

    def test_plain_text_for_mixed_destinations(self):
        self.watch['notification_urls'] = ['tgram://token/chat', 'mailto://user@example.com']
        product_rule_alerts.failure(self.store, self.q, 'w1', 'No price')
        notice = self.q.get_nowait()
        self.assertEqual(notice['notification_format'], 'text')
        self.assertIn('https://example.com/product/123', notice['notification_body'])


if __name__ == '__main__':
    unittest.main()
