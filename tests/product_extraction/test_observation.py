"""Retail rule observation validation, shared by processor and browser readiness."""
import unittest
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location(
    'observation_standalone',
    Path(__file__).parents[2] / 'changedetectionio/product_extraction/observation.py')
observation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observation)
observation_error = observation.observation_error
observation_ready = observation.observation_ready


class ObservationTests(unittest.TestCase):
    def test_all_combinations(self):
        cases = [
            (True, 100, None),
            (True, None, 'price'),
            (False, 100, None),
            (False, None, None),
            (None, 100, 'stock'),
            (None, None, 'stock'),
        ]
        for stock, price, expected in cases:
            with self.subTest(stock=stock, price=price):
                error = observation_error(stock, price)
                self.assertEqual(error is None, expected is None)
                self.assertEqual(observation_ready(stock, price), expected is None)
                if expected:
                    self.assertIn(expected, error)

    def test_false_is_not_unknown(self):
        self.assertIsNone(observation_error(False, None))
        self.assertIsNotNone(observation_error(None, None))
