"""Regression contracts for product-rule readiness and matching."""
import copy
import tempfile
import unittest
from unittest.mock import patch

from changedetectionio.product_extraction.registry import (
    validate, signature, extraction_signature, matches, matching_rules, save,
)
from changedetectionio.product_extraction.models import RuleError


class ProductWaitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rule = {
            'schema_version': 1, 'id': 'store-a', 'name': 'Store A',
            'enabled': True, 'match': {'domains': ['example.com'], 'path_patterns': ['/product/*']},
            'fields': {'price': {'type': 'css', 'value': '.price'}},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_optional_wait_validation(self):
        self.assertEqual(validate(self.rule), self.rule)
        for valid in (0, 5, 30):
            rule = copy.deepcopy(self.rule)
            rule['page'] = {'extra_wait_seconds': valid}
            self.assertEqual(validate(rule)['page']['extra_wait_seconds'], valid)
        for invalid in (-1, 31, 1.5, True, '5'):
            rule = copy.deepcopy(self.rule)
            rule['page'] = {'extra_wait_seconds': invalid}
            with self.assertRaises(RuleError):
                validate(rule)
        with self.assertRaises(RuleError):
            validate({**self.rule, 'page': {'unsupported': 2}})

    def test_wait_or_name_change_preserves_extraction_signature(self):
        rule = copy.deepcopy(self.rule)
        rule['page'] = {'extra_wait_seconds': 8}
        rule['name'] = 'Renamed'
        self.assertNotEqual(signature(rule), signature(self.rule))
        self.assertEqual(extraction_signature(rule), extraction_signature(self.rule))
        rule['fields']['price']['value'] = '#price'
        self.assertNotEqual(extraction_signature(rule), extraction_signature(self.rule))

    def test_matching_uses_registry_url_semantics(self):
        with patch.dict('os.environ', {'PRODUCT_EXTRACTOR_RULES_DIR': self.temp.name}):
            save(self.rule)
            selected = matching_rules('https://www.example.com/product/123')
            self.assertEqual([r['id'] for r in selected], ['store-a'])
            self.assertEqual(matching_rules('https://fakeexample.com/product/123'), [])
            self.assertEqual(matching_rules('https://example.com/not-product'), [])



if __name__ == "__main__":
    unittest.main()
