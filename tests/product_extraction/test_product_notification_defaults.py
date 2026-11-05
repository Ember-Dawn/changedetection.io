"""Non-destructive compact preset initialization across creation/conversion flows."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'changedetectionio/notification/templates.py'

# Execute the real helper against minimal template constants without importing
# the full app, so these regression tests work in lightweight CI environments.
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
          and n.name == 'apply_product_notification_defaults')
# Normal tests should also import the real module in full integration CI.


class ProductNotificationDefaults(unittest.TestCase):
    def test_source_paths_call_shared_initializer(self):
        for path in ('changedetectionio/store/__init__.py',
                     'changedetectionio/blueprint/ui/edit.py',
                     'changedetectionio/blueprint/price_data_follower/__init__.py'):
            with self.subTest(path=path):
                self.assertIn('apply_product_notification_defaults(',
                              (ROOT / path).read_text(encoding='utf-8'))

    def test_helper_has_no_existing_watch_migration(self):
        sources = (ROOT / 'changedetectionio/store/updates.py').read_text(encoding='utf-8')
        self.assertNotIn('apply_product_notification_defaults(', sources)

    def test_helper_behavior(self):
        import sys
        import types
        notification = types.ModuleType('changedetectionio.notification')
        notification.USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH = 'System default'
        original = sys.modules.get('changedetectionio.notification')
        sys.modules['changedetectionio.notification'] = notification
        try:
            module = ast.Module(body=[fn], type_ignores=[])
            namespace = {'PRESETS': [{'id': 'builtin-product-html-compact', 'title': '{{ "" }}',
                                      'body': 'COMPACT', 'format': 'telegram_html'}],
                         'PRODUCT_DEFAULT_TEMPLATE_ID': 'builtin-product-html-compact'}
            exec(compile(ast.fix_missing_locations(module), str(SOURCE), 'exec'), namespace)
            apply = namespace['apply_product_notification_defaults']
            base = {'processor': 'restock_diff', 'notification_format': 'System default'}
            for urls, expected in [(['tgram://key/chat'], True),
                                   (['discord://hook'], False),
                                   (['tgram://a', 'mailto://b'], False),
                                   ([], False)]:
                with self.subTest(urls=urls):
                    watch = dict(base)
                    self.assertEqual(apply(watch, {'notification_urls': urls}), expected)
                    self.assertEqual(watch.get('notification_body'), 'COMPACT' if expected else None)
            watch = dict(base)
            self.assertFalse(apply(watch, {'notification_urls': ['tgram://x']},
                                   explicit_fields={'notification_body'}))
            for value in ('custom', '{{watch_title}}'):
                watch = dict(base, notification_body=value)
                self.assertFalse(apply(watch, {'notification_urls': ['tgram://x']}))
                self.assertEqual(watch['notification_body'], value)
            watch = dict(base, tags=['tag1'])
            self.assertTrue(apply(watch, {'notification_urls': ['discord://x'],
                                          'tags': {'tag1': {'notification_urls': ['tgram://x']}}}))
            watch = dict(base, notification_urls=['discord://x'])
            self.assertFalse(apply(watch, {'notification_urls': ['tgram://x']}))
        finally:
            if original is None: sys.modules.pop('changedetectionio.notification', None)
            else: sys.modules['changedetectionio.notification'] = original

if __name__ == '__main__':
    unittest.main()
