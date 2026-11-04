"""Dependency-free checks of Telegram notification format integration."""
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'changedetectionio/notification/telegram_formats.py'
spec = importlib.util.spec_from_file_location('_telegram_formats_test', FILE)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)


class TelegramFormatsTest(unittest.TestCase):
    def test_telegram_address_and_query_preservation(self):
        self.assertTrue(fmt.is_telegram('tgram://token/chatid?topic=123'))
        self.assertFalse(fmt.is_telegram('mailto://someone@example.com'))
        url = fmt.add_query('tgram://token/chatid?topic=123&format=text',
                            format='html', template='/tmp/rich message.json')
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['topic'], ['123'])
        self.assertEqual(query['format'], ['html'])
        self.assertEqual(query['template'], ['/tmp/rich message.json'])

    def test_json_validation_and_temporary_file(self):
        document = fmt.validate_rich_message(json.dumps({'blocks': [
            {'type': 'details', 'summary': 'Details', 'blocks': [
                {'type': 'paragraph', 'text': '<sample> "title"'}]}]}))
        path = Path(fmt.private_rich_template(document))
        try:
            self.assertEqual(json.loads(path.read_text(encoding='utf8')), document)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        finally:
            path.unlink()
        self.assertFalse(path.exists())

    def test_invalid_payload_is_rejected(self):
        for value in ('not json', '[]', '{}', '{"blocks":[]}',
                      '{"blocks":[{"text":"no type"}]}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fmt.validate_rich_message(value)

    def test_rich_product_preset_has_short_link_and_no_test_heading(self):
        import ast
        from jinja2 import Environment
        source = (ROOT / 'changedetectionio/notification/templates.py').read_text(encoding='utf8')
        module = ast.parse(source)
        template = next(ast.literal_eval(node.value) for node in module.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'PRODUCT_RICH'
                                for t in node.targets))
        context = {
            'watch_title': 'MC 5070 <Ti>',
            'watch_url': 'https://example.com/product?x=1&y=2',
            'watch_open_url': 'https://example.com/product?x=1&y=2',
            'test_notification': True,
            'purchase_alert': {'display_price': '$1,449.99', 'display_change': '',
                               'stock_text': 'Out of stock', 'rule_text': 'Below $1300',
                               'reason_text': 'Rule matched', 'reference_price': None},
        }
        rich = fmt.validate_rich_message(Environment().from_string(template).render(**context))
        blocks = rich['blocks']
        self.assertEqual(blocks[0]['text'], '🛒 MC 5070 <Ti>')
        self.assertEqual(blocks[3]['text'], {'type': 'url',
                                               'text': '🔗 View product',
                                               'url': context['watch_open_url']})
        self.assertIn('Test only', blocks[4]['blocks'][1]['text'])
        self.assertNotIn('TEST', blocks[0]['text'])

    def test_rich_title_field_hides_without_disabling(self):
        js = (ROOT / 'changedetectionio/static/js/notifications.js').read_text(encoding='utf8')
        html = (ROOT / 'changedetectionio/templates/_common_fields.html').read_text(encoding='utf8')
        self.assertIn('id="notification-title-field"', html)
        self.assertIn("$format.val() !== 'telegram_rich'", js)
        self.assertIn("$format.on('change', syncRichTitleVisibility)", js)
        self.assertNotIn("$title.prop('disabled'", js)

    def test_ui_and_dispatch_contract(self):
        notifications = (ROOT / 'changedetectionio/notification/__init__.py').read_text()
        sender = (ROOT / 'changedetectionio/notification/handler.py').read_text()
        templates = (ROOT / 'changedetectionio/notification/templates.py').read_text()
        html = (ROOT / 'changedetectionio/templates/_common_fields.html').read_text()
        for name in ('telegram_html', 'telegram_markdownv2', 'telegram_rich'):
            self.assertIn(name, notifications)
            self.assertIn(name, sender)
            self.assertIn(name, templates)
        self.assertIn('private_rich_template(document)', sender)
        self.assertIn('os.unlink(template_path)', sender)
        self.assertLess(html.index('notification-template-select'),
                        html.index('render_field(form.notification_format'))
        self.assertLess(html.index('render_field(form.notification_format'),
                        html.index('notification-template-preview-result'))


if __name__ == '__main__':
    unittest.main()
