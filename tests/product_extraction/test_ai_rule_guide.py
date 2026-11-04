"""The documented, fictional sample must be directly importable and executable."""
import json
from pathlib import Path
import unittest

from changedetectionio.product_extraction.evaluator import evaluate
from changedetectionio.product_extraction.registry import matches, validate

ROOT = Path(__file__).resolve().parents[2] / 'extractor-rules'


class RuleGuideExampleTests(unittest.TestCase):
    def test_sample_rule_extracts_exact_expected_product(self):
        rule = json.loads((ROOT / 'examples/sample-product-rule.json').read_text(encoding='utf-8'))
        html = (ROOT / 'examples/sample-product.html').read_text(encoding='utf-8')
        validate(rule)
        result = evaluate(rule, html)
        self.assertTrue(matches(rule, 'https://demo.example.com/product/gpu-001'))
        self.assertEqual(result.to_dict(), {
            'price': '1499.99', 'currency': 'USD', 'in_stock': True,
            'stock_quantity': 1, 'pickup': None, 'shipping': None,
            'title': 'Demo Graphics Card',
            'sku': 'GPU-001', 'rule_id': 'sample-product',
        })
        for field in rule['fields']:
            self.assertEqual(result.field_details[field]['matches'], 1)

    def test_guide_and_examples_are_linked(self):
        guide = (ROOT / 'AI_RULE_GUIDE.md').read_text(encoding='utf-8')
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('sample-product.html', guide)
        self.assertIn('sample-product-rule.json', guide)
        self.assertIn('AI_RULE_GUIDE.md', readme)
        self.assertTrue((ROOT / 'schema/product-rule.schema.json').is_file())


if __name__ == '__main__':
    unittest.main()
