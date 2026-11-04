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
