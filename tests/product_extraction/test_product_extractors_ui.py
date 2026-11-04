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
