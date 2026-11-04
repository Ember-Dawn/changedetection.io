"""Product Extractors page integration contracts (no Chromium required)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProductExtractorFrontendContracts(unittest.TestCase):
    def test_template_contains_required_controls(self):
        text = (ROOT / 'changedetectionio/blueprint/product_extractors/templates/product-extractors.html').read_text()
        required = [
            'product-rule-list', 'product-rule-import', 'product-rule-json',
            'product-rule-save', 'product-rule-test', 'product-rule-backend',
            'product-rule-url', 'product-rule-html', 'product-rule-result',
            'product-rule-new', 'product-rule-import-trigger',
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(f'id="{item}"', text)
        self.assertIn("url_for('product_extractors.static', filename='product-extractors.js')", text)
        self.assertIn("url_for('product_extractors.static', filename='product-extractors.css')", text)
        self.assertNotIn('type="file" id="product-rule-import" accept=', text)

    def test_scoped_styles_and_no_inline_js(self):
        path = ROOT / 'changedetectionio/blueprint/product_extractors/templates/product-extractors.html'
        text = path.read_text()
        self.assertNotIn('<script>\n(() =>', text)
        self.assertNotIn('style=', text)
        css = (path.parent.parent / 'static/product-extractors.css').read_text()
        self.assertIn('#px-root .px-button', css)
        self.assertIn('#px-root .px-control', css)
        self.assertIn('appearance:none', css)

    def test_sidebar_uses_available_feather_package_icon(self):
        sidebar = (ROOT / 'changedetectionio/templates/sidebar-nav.html').read_text()
        self.assertIn('data-feather="package" class="action-icon"', sidebar)
        self.assertNotIn('data-feather="package-search"', sidebar)

    def test_backend_static_assets_registered(self):
        code = (ROOT / 'changedetectionio/blueprint/product_extractors/__init__.py').read_text()
        self.assertIn("static_folder='static'", code)


if __name__ == '__main__':
    unittest.main()

class ProductExtractorV2Contracts(unittest.TestCase):
    def test_compact_editor_and_visual_summary_controls(self):
        html=(ROOT/'changedetectionio/blueprint/product_extractors/templates/product-extractors.html').read_text()
        for control in ('product-rule-editor-toggle','product-rule-summary','product-rule-summary-grid',
                        'product-rule-image','product-rule-diagnostics','product-rule-raw-details'):
            self.assertEqual(html.count('id="'+control+'"'),1)
        js=(ROOT/'changedetectionio/blueprint/product_extractors/static/product-extractors.js').read_text()
        self.assertIn('textContent =',js)
        self.assertIn('showPreview(data)',js)
        css=(ROOT/'changedetectionio/blueprint/product_extractors/static/product-extractors.css').read_text()
        self.assertIn('scrollbar-color:',css)
        self.assertIn('grid-template-columns:minmax(0,1fr) auto',css)

    def test_dry_run_uses_one_page_and_does_not_write_history(self):
        code=(ROOT/'changedetectionio/blueprint/product_extractors/__init__.py').read_text()
        self.assertIn("await stepper.page.screenshot(type='jpeg'",code)
        self.assertIn('html_result=await stepper.page.content()',code)
        self.assertIn('return html_result, image_data',code)
        self.assertIn('desktop_viewport()',code)
        self.assertNotIn('send_content_changed_notification(',code)
