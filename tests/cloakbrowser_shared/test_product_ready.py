"""The upstream extraction hook must not fetch another tab while data is loading."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from changedetection_cloak_shared.product_ready import wait_until_ready


class FakePage:
    url = 'https://example.com/product'

    def __init__(self, html_sequence):
        self.html_sequence = list(html_sequence)
        self.calls = 0

    async def content(self):
        result = self.html_sequence[min(self.calls, len(self.html_sequence) - 1)]
        self.calls += 1
        return result


class ProductReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_valid_required_price_on_same_page(self):
        page = FakePage(['loading', 'price: $20'])

        async def no_challenge(_page):
            return None

        def parse_rule(_rule, html):
            return SimpleNamespace(price=20 if '$20' in html else None,
                                   in_stock=None, pickup=None, shipping=None)

        with patch('changedetection_cloak_shared.page_readiness.page_challenge', no_challenge), \
             patch('changedetectionio.product_extraction.evaluate', parse_rule):
            await wait_until_ready(page, {'rule': {}, 'wait_seconds': 2,
                                          'require_price': True, 'require_stock': False})
        self.assertEqual(page.calls, 2)

    async def test_no_wait_when_complete(self):
        page = FakePage(['ready'])

        async def no_challenge(_page):
            return None

        with patch('changedetection_cloak_shared.page_readiness.page_challenge', no_challenge), \
             patch('changedetectionio.product_extraction.evaluate',
                   return_value=SimpleNamespace(price=12, in_stock=None, pickup=None, shipping=None)):
            await wait_until_ready(page, {'rule': {}, 'wait_seconds': 10,
                                          'require_price': True, 'require_stock': False})
        self.assertEqual(page.calls, 1)
