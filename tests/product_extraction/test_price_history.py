"""Focused tests for additive per-check price history and clear races."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / 'changedetectionio/product_extraction/price_history.py'
spec = importlib.util.spec_from_file_location('isolated_price_history', MODULE)
ph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ph)


class PriceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_same_price_every_check_and_null(self):
        gen = ph.generation(self.directory)
        for time in (10, 15, 20):
            self.assertTrue(ph.append(self.directory, timestamp=time, price=123.45,
                                      in_stock=True, expected_generation=gen))
        ph.append(self.directory, timestamp=25, price=None, in_stock=False, expected_generation=gen)
        data = ph.read(self.directory)
        self.assertEqual(len(data), 4)
        self.assertEqual([v['price'] for v in data], [123.45] * 3 + [None])
        self.assertEqual(ph.read(self.directory, since=20)[0]['timestamp'], 20)

    def test_clear_invalidates_in_flight_check(self):
        gen = ph.generation(self.directory)
        ph.append(self.directory, timestamp=10, price=1, in_stock=True, expected_generation=gen)
        ph.clear(self.directory)
        self.assertFalse(ph.append(self.directory, timestamp=11, price=2, in_stock=True,
                                   expected_generation=gen))
        self.assertIsNone(ph.read(self.directory))
        new_gen = ph.generation(self.directory)
        self.assertTrue(ph.append(self.directory, timestamp=12, price=3, in_stock=False,
                                  expected_generation=new_gen))
        self.assertEqual(len(ph.read(self.directory)), 1)

    def test_latest_and_large_same_price_history(self):
        gen = ph.generation(self.directory)
        for timestamp in range(100):
            ph.append(self.directory, timestamp=timestamp, price=1399.99,
                      in_stock=True, expected_generation=gen)
        self.assertEqual(len(ph.read(self.directory)), 100)
        self.assertEqual(ph.latest(self.directory)['timestamp'], 99)
        self.assertTrue(ph.has_records(self.directory))

    def test_missing_directory_not_recreated(self):
        self.directory.rmdir()
        self.assertFalse(ph.append(self.directory, timestamp=1, price=1, in_stock=True))
        self.assertFalse(self.directory.exists())

    def test_malformed_record_ignored(self):
        (self.directory / 'price-history.jsonl').write_text('{broken\n')
        self.assertEqual(ph.read(self.directory), [])

if __name__ == '__main__':
    unittest.main()
