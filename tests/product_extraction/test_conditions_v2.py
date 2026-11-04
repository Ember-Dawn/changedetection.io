"""Synthetic fixtures reflect reported situations; do not claim live site compatibility."""
import json
from pathlib import Path
import importlib.util
import copy
import unittest
from changedetectionio.product_extraction import evaluate, RuleError
from changedetectionio.product_extraction.registry import validate

ROOT=Path(__file__).resolve().parents[2]
RULE=json.loads((ROOT/'extractor-rules/examples/microcenter-composite-demo.json').read_text())
CASES=json.loads((ROOT/'extractor-rules/examples/microcenter-scenarios-fixture.json').read_text())
DOM_RULE=copy.deepcopy(RULE)
DOM_RULE['fields'].pop('currency')
DOM_RULE['fields'].pop('sku')

class ConditionTests(unittest.TestCase):
    def test_all_synthetic_purchase_scenarios(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                result=evaluate(DOM_RULE,case['html'])
                self.assertEqual(result.to_dict()['price'],case['price'])
                for field in ('in_stock','pickup','shipping','stock_quantity'):
                    self.assertEqual(getattr(result,field),case[field])

    def test_tri_state_operators(self):
        r=json.loads(json.dumps(DOM_RULE))
        r['fields']['in_stock']={'condition':{'op':'all','items':[
            {'op':'literal','value':True},{'op':'literal','value':None}]}}
        self.assertIsNone(evaluate(r,CASES[0]['html']).in_stock)
        r['fields']['in_stock']={'condition':{'op':'any','items':[
            {'op':'literal','value':False},{'op':'literal','value':None}]}}
        self.assertIsNone(evaluate(r,CASES[0]['html']).in_stock)
        r['fields']['in_stock']={'condition':{'op':'not','item':{'op':'literal','value':False}}}
        self.assertTrue(evaluate(r,CASES[0]['html']).in_stock)

    def test_condition_guard_cannot_prove_false_without_context(self):
        r=json.loads(json.dumps(DOM_RULE))
        self.assertIsNone(evaluate(r,CASES[-1]['html']).in_stock)

    def test_reject_unknown_operator_and_unbounded_nesting(self):
        r=json.loads(json.dumps(DOM_RULE))
        r['fields']['in_stock']['condition']={'op':'eval','code':'danger()'}
        with self.assertRaises(RuleError):validate(r)
        nested={'op':'literal','value':True}
        for _ in range(12):nested={'op':'not','item':nested}
        r['fields']['in_stock']['condition']=nested
        with self.assertRaises(RuleError):validate(r)

    def test_no_unintended_fallback_when_purchase_unknown(self):
        result=evaluate(DOM_RULE,CASES[-1]['html'])
        self.assertIsNone(result.in_stock)
        self.assertEqual(str(result.price),'189.99')

if __name__=='__main__':unittest.main()
