"""Check the Rich Message internal-title contract without the Web dependencies."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RichTemplateTitleContract(unittest.TestCase):
    def test_server_normalizes_rich_title(self):
        src = (ROOT / 'changedetectionio/notification/templates.py').read_text(encoding='utf-8')
        ast.parse(src)
        self.assertIn("RICH_INTERNAL_TITLE = '{{ watch_title }}'", src)
        self.assertIn("value = RICH_INTERNAL_TITLE if rich and key == 'title'", src)
        self.assertIn("template['title'] = RICH_INTERNAL_TITLE", src)
        self.assertIn("title=RICH_INTERNAL_TITLE, body=PRODUCT_RICH", src)

    def test_frontend_save_update_apply_normalize(self):
        src = (ROOT / 'changedetectionio/static/js/notifications.js').read_text(encoding='utf-8')
        self.assertIn("format === 'telegram_rich' ? richInternalTitle", src)
        self.assertIn("item.format === 'telegram_rich' ? richInternalTitle", src)
        self.assertIn("function mutate(action, item)", src)
        self.assertIn("Object.assign({name:name.trim()},current())", src)
        self.assertIn("Object.assign({id:item.id,name:name.trim()},current())", src)

if __name__ == '__main__':
    unittest.main()
