"""Dependency-free integration contracts for the rule manager and custom dropdowns."""
import ast
import importlib.util
from pathlib import Path
import os
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

class RuleManagerUIContracts(unittest.TestCase):
    def test_copy_duplicate_delete_controls_and_api(self):
        html=(ROOT/'changedetectionio/blueprint/product_extractors/templates/product-extractors.html').read_text()
        js=(ROOT/'changedetectionio/blueprint/product_extractors/static/product-extractors.js').read_text()
        api=(ROOT/'changedetectionio/blueprint/product_extractors/__init__.py').read_text()
        for name in ('product-rule-copy-summary','product-rule-copy-json','product-rule-delete','product-rule-duplicate'):
            self.assertIn(f'id="{name}"', html)
            self.assertIn(f"$('"+name+"')", js)
        for endpoint in ('/api/<rid>/references','/api/<rid>/delete'):
            self.assertIn(endpoint,api)
        self.assertIn('referencing_watches',api)
        self.assertIn('expected_signature',js)

    def test_shared_custom_dropdown_preserves_native_controls(self):
        views=['changedetectionio/blueprint/manual_browser/templates/manual-browser.html',
               'changedetectionio/blueprint/product_extractors/templates/product-extractors.html']
        for rel in views:
            html=(ROOT/rel).read_text()
            self.assertIn('data-custom-select',html)
            self.assertIn('css/custom-select.css',html)
            self.assertIn('js/custom-select.js',html)
        code=(ROOT/'changedetectionio/static/js/custom-select.js').read_text()
        self.assertIn("new Event('change', {bubbles:true})",code)
        self.assertIn("document.body.append(list)",code)
        for key in ('ArrowDown','ArrowUp','Escape','Home','End'):
            self.assertIn(key,code)

    def test_one_configurable_viewport_source(self):
        module=ROOT/'changedetectionio/product_extraction/viewport.py'
        ast.parse(module.read_text())
        spec=importlib.util.spec_from_file_location('desktop_viewport_unit',module)
        loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(loaded.desktop_viewport(),{'width':1366,'height':900})
        with patch.dict(os.environ,{'CLOAKBROWSER_VIEWPORT_WIDTH':'1440','CLOAKBROWSER_VIEWPORT_HEIGHT':'950'}):
            self.assertEqual(loaded.desktop_viewport(),{'width':1440,'height':950})
        with patch.dict(os.environ,{'CLOAKBROWSER_VIEWPORT_WIDTH':'99999','CLOAKBROWSER_VIEWPORT_HEIGHT':'bad'}):
            self.assertEqual(loaded.desktop_viewport(),{'width':2560,'height':900})
        manager=(ROOT/'integrations/cloakbrowser-shared/changedetection_cloak_shared/manager.py').read_text()
        dry=(ROOT/'changedetectionio/blueprint/product_extractors/__init__.py').read_text()
        self.assertIn('desktop_viewport()',manager)
        self.assertIn('desktop_viewport()',dry)
        manual=(ROOT/'changedetectionio/blueprint/manual_browser/static/manual-layout.js').read_text()
        self.assertIn('fixedViewport',manual)
        self.assertIn("root.style.height = 'auto'",manual)

if __name__=='__main__':unittest.main()
