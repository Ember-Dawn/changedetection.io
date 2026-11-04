"""Self-contained registry lifecycle tests, no Flask or browser dependencies."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_registry():
    package = 'test_rule_registry_package'
    parent = sys.modules.setdefault(package, types.ModuleType(package))
    parent.__path__ = [str(ROOT / 'changedetectionio/product_extraction')]
    for name in ('models', 'registry'):
        full = f'{package}.{name}'
        spec = importlib.util.spec_from_file_location(full, ROOT/'changedetectionio/product_extraction'/f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
    return sys.modules[f'{package}.registry']


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = load_registry()
        self.registry.root = lambda: Path(self.temp.name)

    def rule(self, price='.price'):
        return {'schema_version': 1, 'id': 'example-products', 'name': 'Example',
                'match': {'domains': ['example.com'], 'path_patterns': ['/p/*']},
                'fields': {'price': {'selectors': [{'type': 'css', 'value': price, 'extract': 'text'}]}}}

    def test_duplicate_is_noop_but_changed_id_requires_explicit_update(self):
        r = self.registry
        old = self.rule()
        self.assertEqual(r.save(old, return_status=True)[1], 'created')
        self.assertEqual(r.save(old, return_status=True)[1], 'unchanged')
        newer = self.rule('.newprice')
        with self.assertRaisesRegex(r.RuleError, 'exists'):
            r.save(newer)
        with self.assertRaisesRegex(r.RuleError, 'reload'):
            r.save(newer, overwrite=True)
        revision = r.signature(old)
        self.assertEqual(r.save(newer, overwrite=True, expected_signature=revision, return_status=True)[1], 'updated')
        with self.assertRaisesRegex(r.RuleError, 'changed'):
            r.save(old, overwrite=True, expected_signature=revision)
        self.assertEqual(r.load(old['id']), newer)

    def test_deletion_requires_current_revision(self):
        r = self.registry
        rule = self.rule()
        r.save(rule)
        with self.assertRaisesRegex(r.RuleError, 'reload'):
            r.remove(rule['id'])
        r.remove(rule['id'], expected_signature=r.signature(rule))
        self.assertFalse((Path(self.temp.name)/'rules'/'example-products.json').exists())
        self.assertEqual(r.list_rules(), [])

    def test_rule_id_is_the_unique_git_filename_and_revision_in_list(self):
        r = self.registry
        rule = self.rule()
        r.save(rule)
        entry = r.list_rules()[0]
        self.assertEqual(entry['id'],rule['id'])
        self.assertEqual(entry['revision'],r.signature(rule))
        self.assertEqual(len(list((Path(self.temp.name)/'rules').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
