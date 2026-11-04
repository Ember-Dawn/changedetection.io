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

    def test_purchase_form_declares_new_price_stock_modes_and_rules(self):
        source = (ROOT / 'changedetectionio/processors/restock_diff/forms.py').read_text()
        for mode in ('percent_down', 'percent_up', 'percent_any', 'any_change',
                     'in_stock', 'out_of_stock', 'restock', 'sold_out'):
            self.assertIn("'" + mode + "'", source)
        self.assertIn('price_threshold = FloatField(', source)
        self.assertIn('price_follow_changes = BooleanField(', source)
        self.assertIn("default='and'", source)
        self.assertIn('purchase-copy-rules', source)
        self.assertIn('STOCK_PRICE_RULES.md', source)
        self.assertIn('data-custom-select', source)
        self.assertIn("r['name'], r['id']", source)
        self.assertNotIn("{{ url_for('static'", source)

    def test_editor_no_duplicate_manual_button(self):
        source = (ROOT / 'changedetectionio/blueprint/ui/templates/edit.html').read_text()
        self.assertNotIn('class="pure-button pure-button-primary">人工操作', source)
        self.assertIn("url_for('static', filename='js/custom-select.js')", source)

    def test_api_and_docs_reference_new_modes(self):
        schema = (ROOT / 'changedetectionio/processors/restock_diff/api.yaml').read_text()
        doc = (ROOT / 'docs/product-extraction/STOCK_PRICE_RULES.md').read_text()
        for mode in ('percent_down', 'percent_up', 'percent_any', 'sold_out', 'in_stock'):
            self.assertIn(mode, schema)
            self.assertIn(mode, doc)
        self.assertIn('price_follow_changes', schema)
        self.assertIn('AND', doc)
        self.assertIn('OR', doc)

    def test_watch_model_persists_purchase_state(self):
        source = (ROOT / 'changedetectionio/model/__init__.py').read_text()
        self.assertIn("'purchase_alert_state': {}", source)
        source = (ROOT / 'changedetectionio/processors/restock_diff/__init__.py').read_text()
        self.assertIn("values['purchase_alert']", source)


if __name__ == '__main__':
    unittest.main()
