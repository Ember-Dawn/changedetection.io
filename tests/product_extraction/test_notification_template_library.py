"""Notification template library: storage, rendering, and no-send preview."""
import unittest
import pytest
pytest.importorskip("flask")
pytest.importorskip("loguru")
from flask import Flask
from changedetectionio.notification.templates import PRESETS, get_templates, mutate_templates
from changedetectionio.jinja2_custom import render
from changedetectionio.processors.restock_diff import _reason_description, _rule_description
from changedetectionio.blueprint.ui.notification import construct_blueprint


class FakeStore:
    def __init__(self):
        self.data = {'settings': {'application': {}}, 'watching': {}}
        self.commits = 0
    def commit(self):
        self.commits += 1


class TemplateLibraryTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()

    def test_builtin_ids_names_and_order(self):
        self.assertEqual([(item['id'], item['name']) for item in PRESETS], [
            ('builtin-general', 'General webpage change'),
            ('builtin-product-text', 'Product · Plain Text'),
            ('builtin-compact', 'Compact change alert'),
            ('builtin-product-html-compact', 'Telegram product · HTML (compact)'),
            ('builtin-product-html-expanded', 'Telegram product · HTML (all details)'),
            ('builtin-product-rich', 'Telegram product · Rich (all details)'),
        ])

    def test_presets_render_with_sample_context(self):
        for preset in PRESETS:
            self.assertTrue(preset['title'])
            self.assertTrue(preset['body'])
            text = render(preset['body'], watch_url='https://example.test',
                          watch_title='Example', watch_open_url='https://example.test',
                          restock={'price': 1200, 'currency': 'USD', 'in_stock': True, 'title':'Example'},
                          purchase_alert={'show_price':True,'show_stock':True,
                                          'display_price':'$1,200.00','display_change':'(−4%, ↓ $50.00)',
                                          'display_stock':'✅ In stock','display_stock_current':'✅ In stock',
                                          'display_reference_price':'$1,250.00',
                                          'stock_text':'In stock','reason_text':'Price fell',
                                          'rule_text':'price below 1300', 'reference_price':1250,
                                          'price_change_amount':-50, 'percent_change':-4}, diff='changed')
            self.assertTrue(text)

    def test_create_update_delete_and_preset_protection(self):
        item = {'name': 'My Product', 'title': 'T {{ watch_title }}', 'body': 'B {{ restock.price }}', 'format':'text'}
        created = mutate_templates(self.store, 'create', item)
        self.assertEqual(len(get_templates(self.store)), len(PRESETS) + 1)
        self.assertEqual(self.store.commits, 1)
        changed = mutate_templates(self.store, 'update', dict(item, id=created['id'], name='Renamed'))
        self.assertEqual(changed['name'], 'Renamed')
        with self.assertRaises(ValueError):
            mutate_templates(self.store, 'delete', {'id':'builtin-product'})
        mutate_templates(self.store, 'delete', {'id':created['id']})
        self.assertEqual(len(get_templates(self.store)), len(PRESETS))
        self.assertEqual(self.store.commits, 3)

    def test_unicode_template_names(self):
        entry = mutate_templates(self.store,'create',
            {'name':'显卡降价与补货提醒 ✅','title':'标题', 'body':'价格', 'format':'telegram_html'})
        self.assertEqual(entry['name'], '显卡降价与补货提醒 ✅')

    def test_validation(self):
        with self.assertRaises(ValueError):
            mutate_templates(self.store, 'create', {'name':'x','title':'t','body':'b','format':'evil'})
        with self.assertRaises(Exception):
            mutate_templates(self.store, 'create', {'name':'x','title':'{{', 'body':'b','format':'text'})
        self.assertEqual(self.store.commits, 0)

    def test_watch_rule_description(self):
        state = {'price_mode':'below','stock_mode':'in_stock','price_threshold':'1300',
                 'combine_mode':'and','last_alert_reason':'price+stock_filter',
                 'last_alert_price_direction':'down','last_alert_previous_stock':False,
                 'last_stock':True}
        self.assertIn('1300', _rule_description(state, 'USD'))
        self.assertIn('AND', _rule_description(state, 'USD'))
        self.assertIn('Price', _reason_description(state))

    def test_http_preview_does_not_send_or_commit(self):
        app = Flask(__name__)
        app.config.update(SECRET_KEY='test', DATASTORE=self.store, LOGIN_DISABLED=True)
        app.register_blueprint(construct_blueprint(self.store))
        client = app.test_client()
        self.assertEqual(client.get('/notification/templates').status_code, 200)
        resp = client.post('/notification/template-preview', json={
            'title':'Alert {{ watch_title }}',
            'body':'{{ purchase_alert.reason_text }} | {{ restock.price }}',
            'format':'text'
        })
        self.assertEqual(resp.status_code,200,resp.get_data(as_text=True))
        self.assertIn('1199.99',resp.json['body'])
        self.assertEqual(resp.json['source'],'example')
        self.assertEqual(self.store.commits,0)
        self.assertEqual(client.post('/notification/template-preview',json={'title':'{{','body':'X','format':'text'}).status_code,400)


if __name__ == '__main__':
    unittest.main()
