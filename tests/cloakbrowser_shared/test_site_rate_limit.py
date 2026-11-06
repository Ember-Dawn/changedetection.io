"""Unit checks for per-site start-time spacing (no browser required)."""
import asyncio
import importlib.util
import pathlib
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/site_rate_limit.py'
spec = importlib.util.spec_from_file_location('site_rate_limit_under_test', SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def offline_extract(host):
    if host.endswith('.co.uk'):
        part = host.split('.')
        domain = '.'.join(part[-3:])
    else:
        domain = '.'.join(host.split('.')[-2:])
    return SimpleNamespace(top_domain_under_public_suffix=domain)


class Tests(unittest.TestCase):
    def setUp(self):
        module._EXTRACT = offline_extract

    def test_domain_grouping(self):
        self.assertEqual(module.site_key('https://www.microcenter.com/product/123'), 'microcenter.com')
        self.assertEqual(module.site_key('https://store.example.co.uk/one'), 'example.co.uk')
        self.assertEqual(module.site_key('https://example.co.uk/two'), 'example.co.uk')

    def test_overrides(self):
        self.assertEqual(module.parse_overrides('microcenter.com = 10\namazon.com=5'),
                         {'microcenter.com': 10, 'amazon.com': 5})
        self.assertEqual(module.effective_interval('microcenter.com', {
            'site_interval_seconds': 3, 'site_interval_overrides': 'microcenter.com=10'}), 10)
        for bad in ['https://example.com=3', 'example.com=-1', 'example.com=inf',
                    'example.com = 3\nexample.com = 5', 'example.com = junk']:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    module.parse_overrides(bad)

    def test_spacing_same_site_and_independent_sites(self):
        async def check():
            times = []
            now = [100.]
            async def sleep(seconds):
                now[0] += seconds
                await asyncio.sleep(0)
            pacer = module.SiteNavigationPacer(clock=lambda: now[0], sleep=sleep)
            settings = {'site_interval_seconds':3, 'site_interval_overrides': 'microcenter.com=10'}
            await asyncio.gather(*(pacer.wait_turn(u, settings) for u in [
                'https://www.microcenter.com/a',
                'https://www.microcenter.com/b',
                'https://www.microcenter.com/c']))
            self.assertEqual(now[0], 120)
            await pacer.wait_turn('https://amazon.com/product', settings)
            self.assertEqual(now[0], 120)
            await pacer.wait_turn('https://www.microcenter.com/d', {'site_interval_seconds':0})
            self.assertEqual(now[0], 120)
        asyncio.run(check())

if __name__ == '__main__':
    unittest.main()
