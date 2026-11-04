"""Dependency-free checks for the notification template UI and saved event fields."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NotificationTemplateContract(unittest.TestCase):
    def test_shared_form_uses_authenticated_endpoint_names(self):
        form = (ROOT / 'changedetectionio/templates/_common_fields.html').read_text()
        self.assertIn("url_for('ui.ui_notification.notification_templates_api')", form)
        self.assertIn("url_for('ui.ui_notification.notification_template_preview')", form)
        self.assertIn('notification-template-select', form)
        self.assertIn('notification-template-preview-result', form)

    def test_preview_does_not_trigger_notification(self):
        source = (ROOT / 'changedetectionio/blueprint/ui/notification.py').read_text()
        section = source.split('def notification_template_preview():', 1)[1].split('# AJAX endpoint for sending a test', 1)[0]
        self.assertNotIn('process_notification(', section)
        self.assertNotIn('datastore.commit(', section)
        self.assertIn('render_jinja(', section)

    def test_js_text_only_preview_and_csrf(self):
        js = (ROOT / 'changedetectionio/static/js/notifications.js').read_text()
        self.assertIn("$('#notification-template-preview-body').text(data.body)", js)
        self.assertIn("'X-CSRFToken': csrf", js)
        self.assertIn('setupNotificationTemplateLibrary()', js)
        self.assertNotIn("$('#notification-template-preview-body').html(data.body)", js)

    def test_purchase_alert_saves_reference_for_notifications(self):
        file = ROOT / 'changedetectionio/processors/restock_diff/purchase_alert.py'
        spec = importlib.util.spec_from_file_location('_purchase_notify_test', file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        settings = {'price_mode': 'below', 'stock_mode': 'in_stock',
                    'price_threshold': 1300, 'combine_mode': 'and',
                    'price_follow_changes': True}
        product = lambda price: {'in_stock': True, 'price': price, 'currency': 'USD'}
        _, state, _ = mod.evaluate_purchase_alert(settings, product(1400))
        triggered, state, _ = mod.evaluate_purchase_alert(settings, product(1250), state)
        self.assertTrue(triggered)
        self.assertEqual(state['last_alert_reference_price'], '1400')
        self.assertEqual(state['last_alert_price_change_amount'], '-150')


if __name__ == '__main__':
    unittest.main()
