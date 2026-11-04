"""Static contract checks that run without Flask/WTF/runtime browser dependencies."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PurchaseWiringContract(unittest.TestCase):
    def test_processor_uses_new_evaluator_not_legacy_filters(self):
        source = (ROOT / 'changedetectionio/processors/restock_diff/processor.py').read_text()
        self.assertIn('evaluate_purchase_alert(', source)
        self.assertIn("update_obj['purchase_alert_state']", source)
        self.assertNotIn("restock_settings.get('follow_price_changes')", source)
        self.assertNotIn("restock_settings.get('price_change_min')", source)
        self.assertNotIn("restock_settings.get('in_stock_processing')", source)

    def test_first_check_worker_delivery_gate_untouched(self):
        worker = (ROOT / 'changedetectionio/worker.py').read_text()
        self.assertIn('if watch.history_n >= 2:', worker)
        self.assertIn('if changed_detected or not watch.history_n:', worker)

    def test_purchase_form_declares_three_modes_and_target(self):
        source = (ROOT / 'changedetectionio/processors/restock_diff/forms.py').read_text()
        for mode in ('stock_and_price', 'stock_only', 'price_only'):
            self.assertIn("'" + mode + "'", source)
        self.assertIn('target_price = FloatField(', source)
        self.assertIn('data-custom-select', source)
        self.assertIn("r['name'], r['id']", source)
        self.assertIn('purchase-radio li', source)
        self.assertNotIn('price_change_threshold_percent', source)
        # The extra_form_content fragment is rendered through a plain Jinja2 Environment
        # (not Flask's), so static asset URLs must live in edit.html instead.
        self.assertNotIn("{{ url_for('static'", source)

    def test_editor_no_duplicate_manual_button(self):
        source = (ROOT / 'changedetectionio/blueprint/ui/templates/edit.html').read_text()
        self.assertNotIn('class="pure-button pure-button-primary">人工操作', source)
        self.assertIn("url_for('static', filename='js/custom-select.js')", source)

    def test_api_and_docs_reference_new_modes(self):
        schema = (ROOT / 'changedetectionio/processors/restock_diff/api.yaml').read_text()
        doc = (ROOT / 'docs/product-extraction/RESTOCK_AND_ALERTS.md').read_text()
        for mode in ('stock_and_price', 'stock_only', 'price_only'):
            self.assertIn(mode, schema)
            self.assertIn(mode, doc)
        self.assertIn('price change', doc.lower())

    def test_watch_model_persists_purchase_state(self):
        source = (ROOT / 'changedetectionio/model/__init__.py').read_text()
        self.assertIn("'purchase_alert_state': {}", source)
        source = (ROOT / 'changedetectionio/processors/restock_diff/__init__.py').read_text()
        self.assertIn("values['purchase_alert']", source)


if __name__ == '__main__':
    unittest.main()
