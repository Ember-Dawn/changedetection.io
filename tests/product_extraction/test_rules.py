"""Pure rule-engine regression tests; no real browser or Telegram involved."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import importlib.util
from changedetectionio.product_extraction import (evaluate, choose, load, save, RuleError)
from changedetectionio.product_extraction.registry import signature


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.old=os.environ.get('PRODUCT_EXTRACTOR_RULES_DIR')
        self.temp=tempfile.TemporaryDirectory()
        os.environ['PRODUCT_EXTRACTOR_RULES_DIR']=self.temp.name
        sample=Path(__file__).resolve().parents[2]/'extractor-rules/examples/example-product.json'
        self.rule=json.loads(sample.read_text())

    def tearDown(self):
        if self.old is None:os.environ.pop('PRODUCT_EXTRACTOR_RULES_DIR',None)
        else:os.environ['PRODUCT_EXTRACTOR_RULES_DIR']=self.old
        self.temp.cleanup()

    def test_read_write_and_match(self):
        save(self.rule)
        self.assertEqual(load('example-store')['name'],self.rule['name'])
        self.assertEqual(choose('https://example.com/product/1')['id'],'example-store')
        self.assertIsNone(choose('https://someexample.com/product/1'))
        self.assertIsNone(choose('https://example.com/other'))
        self.assertIsNone(choose('https://example.com/product/1','builtin'))
        self.assertEqual(choose('https://example.com/product/1','rule','example-store')['id'],'example-store')
        with self.assertRaises(RuleError): choose('https://example.org/product/1','rule','example-store')

    def test_price_and_stock(self):
        result=evaluate(self.rule,'<b class="product-price">$1,499.99</b><div class="stock-indicator">In Stock</div>')
        self.assertEqual(result.to_dict()['price'],'1499.99')
        self.assertTrue(result.in_stock)
        self.assertEqual(result.rule_id,'example-store')
        self.assertEqual(result.field_details['price']['matches'],1)

    def test_stock_only_and_unknown(self):
        rule=dict(self.rule);rule['fields']={'in_stock':self.rule['fields']['in_stock']}
        self.assertFalse(evaluate(rule,'<div class="stock-indicator">Out of Stock</div>').in_stock)
        rule['fields']['price']=self.rule['fields']['price']
        got=evaluate(rule,'<div class="product-price">$29.99</div>')
        self.assertIsNone(got.in_stock)

    def test_quantity_infers_stock(self):
        rule=dict(self.rule)
        rule['fields']={'stock_quantity':{'type':'css','value':'.quantity'}}
        result=evaluate(rule,'<span class="quantity">0</span>')
        self.assertEqual(result.stock_quantity,0)
        self.assertFalse(result.in_stock)

    @unittest.skipUnless(importlib.util.find_spec('jsonpath_ng'), 'jsonpath-ng is not installed locally')
    def test_jsonld_jsonpath(self):
        rule=dict(self.rule)
        rule['fields']={'price':{'type':'jsonpath','value':'$..price'}}
        html='<script type="application/ld+json">{"offers":{"price":"49.99"}}</script>'
        self.assertEqual(evaluate(rule,html).to_dict()['price'],'49.99')

    def test_ambiguous_price_fails(self):
        with self.assertRaisesRegex(RuleError,'Ambiguous'):
            evaluate(self.rule,'<b class="product-price">$10</b><b class="product-price">$20</b>')

    def test_rule_signature_changes(self):
        original=signature(self.rule)
        self.rule['fields']['price']['selectors'][0]['value']='#somewhere-else'
        self.assertNotEqual(original,signature(self.rule))

    def test_rule_fails_closed(self):
        bad=dict(self.rule);bad['id']='../../etc/passwd'
        with self.assertRaises(RuleError):save(bad)
        self.assertFalse(list((Path(self.temp.name)/'rules').glob('*.json')))

    def test_xpath(self):
        rule=dict(self.rule);rule['fields']={'price':{'type':'xpath','value':'//strong[@id="price"]'}}
        result=evaluate(rule,'<strong id="price">$39.99</strong>')
        self.assertEqual(result.to_dict()['price'],'39.99')

    def test_regex(self):
        rule=dict(self.rule);rule['fields']={'price':{'type':'regex','value':'PRICE: ([0-9.]+)'}}
        result=evaluate(rule,'PRICE: 12.50')
        self.assertEqual(result.to_dict()['price'],'12.50')

    def test_disabled_rule_is_not_selected(self):
        self.rule['enabled']=False
        save(self.rule)
        self.assertIsNone(choose('https://example.com/product/1'))
        with self.assertRaises(RuleError):
            choose('https://example.com/product/1','rule','example-store')
        self.assertIsNotNone(evaluate(self.rule,'<b class="product-price">$8.99</b>'))

    def test_symlink_refused(self):
        save(self.rule)
        target=Path(self.temp.name)/'rules'/'example-store.json'
        target.unlink();target.symlink_to('/etc/hosts')
        with self.assertRaises(RuleError):load('example-store')
        with self.assertRaises(RuleError):save(self.rule)

if __name__=='__main__':unittest.main()
