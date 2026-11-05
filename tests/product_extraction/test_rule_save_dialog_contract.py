"""Regression checks for the Product Extractors save/confirmation contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / 'changedetectionio/blueprint/product_extractors'


class RuleSaveDialogContract(unittest.TestCase):
    def test_loaded_rule_saves_without_confirmation_but_collision_asks(self):
        js = (UI / 'static/product-extractors.js').read_text()
        self.assertIn('currentId !== payload.id && !await askConfirm(', js)
        self.assertIn('overwrite:Boolean(existing)', js)
        self.assertIn('expected_signature:existing ? revisions.get(payload.id) : null', js)
        self.assertNotIn('window.confirm(', js)
        self.assertNotIn('window.alert(', js)

    def test_dialog_keyboard_and_accessibility(self):
        html = (UI / 'templates/product-extractors.html').read_text()
        js = (UI / 'static/product-extractors.js').read_text()
        css = (UI / 'static/product-extractors.css').read_text()
        for control in ('px-confirm-dialog', 'px-confirm-title', 'px-confirm-description',
                        'px-confirm-cancel', 'px-confirm-accept'):
            self.assertEqual(html.count('id="' + control + '"'), 1)
        self.assertIn('aria-modal="true"', html)
        self.assertIn("event.key === 'Enter' && !event.isComposing", js)
        self.assertIn("event.key === 'Escape'", js)
        self.assertIn("event.key === 'Tab'", js)
        self.assertIn('dialogPreviousFocus.focus()', js)
        self.assertIn('.px-dialog-overlay[hidden]{display:none}', css)

    def test_registry_retains_revision_guard(self):
        registry = (ROOT / 'changedetectionio/product_extraction/registry.py').read_text()
        self.assertIn("if not overwrite:", registry)
        self.assertIn('expected_signature!=signature(existing)', registry)


if __name__ == '__main__':
    unittest.main()
