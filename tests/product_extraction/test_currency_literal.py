"""Currency literal is deliberately exclusive to currency and is not selector fallback."""
import copy
import json
from pathlib import Path
import unittest

from changedetectionio.product_extraction.evaluator import evaluate
from changedetectionio.product_extraction.registry import extraction_signature, validate
from changedetectionio.product_extraction.models import RuleError

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / 'extractor-rules/examples/sample-product-rule.json').read_text(encoding='utf-8'))
HTML = (ROOT / 'extractor-rules/examples/sample-product.html').read_text(encoding='utf-8')


class CurrencyLiteralTests(unittest.TestCase):
    def rule(self):
        return copy.deepcopy(BASE)

    def test_fixed_currency_without_currency_element(self):
        rule = self.rule()
        rule['fields']['currency'] = {'literal': 'USD'}
        html = HTML.replace('USD', '---')
        result = evaluate(rule, html)
        self.assertEqual(result.currency, 'USD')
        self.assertIsNone(result.field_details['currency']['selector'])
        self.assertEqual(result.field_details['currency']['values'], ['USD'])

    def test_existing_selector_behavior_and_signature_unchanged(self):
        rule = self.rule()
        old_signature = extraction_signature(rule)
        self.assertEqual(evaluate(rule, HTML).currency, 'USD')
        self.assertEqual(extraction_signature(rule), old_signature)
        self.assertEqual(validate(rule), rule)

    def test_currency_omitted_remains_unknown(self):
        rule = self.rule()
        del rule['fields']['currency']
        self.assertIsNone(evaluate(rule, HTML).currency)

    def test_currency_literal_changes_extraction_signature(self):
        rule = self.rule()
        old = extraction_signature(rule)
        rule['fields']['currency'] = {'literal': 'USD'}
        self.assertNotEqual(old, extraction_signature(rule))

    def test_other_iso_currencies(self):
        for code in ['USD', 'EUR', 'GBP', 'JPY', 'CAD']:
            with self.subTest(code=code):
                rule = self.rule()
                rule['fields']['currency'] = {'literal': code}
                self.assertEqual(evaluate(rule, HTML).currency, code)

    def test_invalid_and_mixed_currency_rules(self):
        for spec in [
            {'literal': '$'}, {'literal': 'usd'}, {'literal': 'USDT'},
            {'literal': ''}, {'literal': None}, {'literal': 'ZZZ'},
            {'literal': 123}, {'literal': 'USD', 'type': 'css', 'value': '.currency'},
            {'literal': 'USD', 'selectors': [{'type':'css','value':'.currency'}]},
            {'literal': 'USD', 'condition': {'op': 'literal', 'value': True}},
        ]:
            with self.subTest(spec=spec):
                rule = self.rule()
                rule['fields']['currency'] = spec
                with self.assertRaises(RuleError):
                    validate(rule)

    def test_other_fields_do_not_accept_literal(self):
        for field in ['price', 'title', 'sku', 'stock_quantity', 'pickup', 'shipping', 'in_stock']:
            with self.subTest(field=field):
                rule = self.rule()
                rule['fields'][field] = {'literal': 'USD'}
                with self.assertRaises(RuleError):
                    validate(rule)

    def test_json_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest('jsonschema not installed')
        schema = json.loads((ROOT / 'extractor-rules/schema/product-rule.schema.json').read_text())
        good = self.rule()
        good['fields']['currency'] = {'literal':'USD'}
        jsonschema.validate(good, schema)
        for spec in [{'literal':'USD','selectors':[{'type':'css','value':'.x'}]}, {'literal':'usd'}]:
            bad = self.rule()
            bad['fields']['currency'] = spec
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)
        jsonschema.validate(self.rule(), schema)


if __name__ == '__main__':
    unittest.main()
