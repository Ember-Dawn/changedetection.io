"""Offline regression checks for the complete dynamic product-preset matrix."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[2]


def constants():
    tree = ast.parse((ROOT / 'changedetectionio/notification/templates.py').read_text(encoding='utf-8'))
    result = {}
    for item in tree.body:
        if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
            if isinstance(item.value, ast.Constant):
                result[item.targets[0].id] = item.value.value
    return result


def context(price, stock, test=False):
    return {
        'watch_title': '显卡 <Ti> & 价格',
        'watch_open_url': 'https://example.org/p?a=1&b=2',
        'watch_url': 'https://example.org/p',
        'test_notification': test,
        'purchase_alert': {
            'show_price': price, 'show_stock': stock,
            'display_price': '$890.00',
            'display_change': '(−11%, ↓ $110.00)',
            'display_stock': '✅ Restocked',
            'display_stock_current': '✅ In stock',
            'display_reference_price': '$1,000.00',
            'rule_text': 'Price down ≥ 10% OR restock',
            'reason_text': 'Both thresholds triggered',
        },
    }


class TitleLinkParser(HTMLParser):
    links = None
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.in_link = False
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append([dict(attrs).get('href'), ''])
            self.in_link = True
    def handle_data(self, data):
        if self.in_link:
            self.links[-1][1] += data
    def handle_endtag(self, tag):
        if tag == 'a':
            self.in_link = False


class DynamicProductPresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = constants()
        cls.env = Environment()

    def render(self, key, price, stock, test=False):
        return self.env.from_string(self.values[key]).render(**context(price, stock, test)).strip()

    def test_title_is_escaped_chinese_clickable_link(self):
        rendered = self.render('PRODUCT_HTML_COMPACT', True, True)
        self.assertEqual(self.env.from_string(self.values['PRODUCT_HTML_TITLE']).render(**context(True, True)), '')
        parser = TitleLinkParser()
        parser.feed(rendered)
        self.assertEqual(parser.links, [['https://example.org/p?a=1&b=2', '显卡 <Ti> & 价格']])
        self.assertIn('<b>', rendered)
        self.assertIn('&lt;Ti&gt;', rendered)

    def test_both_html_variants_and_plain_text_follow_price_stock_flags(self):
        for key in ('PRODUCT_HTML', 'PRODUCT_HTML_EXPANDED', 'PRODUCT_HTML_COMPACT', 'PRODUCT_TEXT'):
            for price, stock in ((True, False), (False, True), (True, True), (False, False)):
                with self.subTest(key=key, price=price, stock=stock):
                    rendered = self.render(key, price, stock)
                    self.assertEqual('💰 $890.00' in rendered, price)
                    self.assertEqual('✅ Restocked' in rendered, stock)
                    self.assertEqual('−11%' in rendered, price)
                    self.assertNotIn('📦', rendered)

    def test_details_are_only_in_expandable_or_inline_detail_presets(self):
        fold = self.render('PRODUCT_HTML', True, True)
        expanded = self.render('PRODUCT_HTML_EXPANDED', True, True)
        compact = self.render('PRODUCT_HTML_COMPACT', True, True)
        self.assertIn('<blockquote expandable>', fold)
        self.assertNotIn('<blockquote', expanded)
        self.assertIn('🎯', expanded)
        self.assertNotIn('<blockquote', compact)
        self.assertNotIn('🎯', compact)
        self.assertNotIn('🔔', compact)
        self.assertNotIn('📊', compact)
        self.assertNotIn('View product', compact)

    def test_test_notification_does_not_claim_event_or_baseline(self):
        for key in ('PRODUCT_HTML', 'PRODUCT_HTML_EXPANDED', 'PRODUCT_HTML_COMPACT', 'PRODUCT_TEXT'):
            with self.subTest(key=key):
                result = self.render(key, True, True, True)
                self.assertNotIn('−11%', result)
                self.assertNotIn('Restocked', result)
                if key != 'PRODUCT_HTML_COMPACT':
                    self.assertIn('Test notification', result)
                    self.assertNotIn('Reference:', result)

    def test_template_ui_uses_custom_dialog_and_save_guard(self):
        js = (ROOT / 'changedetectionio/static/js/notifications.js').read_text(encoding='utf-8')
        shared = (ROOT / 'changedetectionio/templates/_common_fields.html').read_text(encoding='utf-8')
        self.assertNotIn('window.prompt(', js)
        self.assertNotIn('window.confirm(', js)
        self.assertIn('setFormat(item.format);', js)
        self.assertIn("$select.on('change', function()", js)
        self.assertIn("$select.closest('form').on('submit.notificationTemplateGuard'", js)
        self.assertIn("e.key === 'Enter'", js)
        self.assertIn("e.key === 'Escape'", js)
        self.assertIn('role="dialog" aria-modal="true"', shared)


if __name__ == '__main__':
    unittest.main()
