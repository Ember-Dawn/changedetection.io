"""No real browser/network: early challenge checks and notification state transitions."""
import asyncio
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from loguru import logger
except ImportError:
    fake_loguru = types.ModuleType('loguru')
    fake_loguru.logger = types.SimpleNamespace(info=lambda *a, **kw: None,
                                                warning=lambda *a, **kw: None,
                                                debug=lambda *a, **kw: None)
    sys.modules['loguru'] = fake_loguru

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manager import _ManagedPage, _SHARED_FETCH
from changedetection_cloak_shared.page_readiness import challenge_kind


class FakePage:
    url = 'https://www.microcenter.com/product/example'

    def __init__(self, text):
        self.text = text
        self.waited = []

    async def wait_for_timeout(self, ms):
        self.waited.append(ms)

    async def evaluate(self, script):
        return {'title': 'Just a moment...', 'url': self.url, 'text': self.text}


class EarlyChallengeTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_scholar_detected_before_extraction(self):
        p = FakePage('请进行人机身份验证')
        p.url = 'https://scholar.google.com.hk/citations?user=x'
        lease = _ManagedPage(p, asyncio.Semaphore(1))
        fake = types.ModuleType('changedetectionio.content_fetchers.exceptions')
        class PageUnloadable(Exception):
            def __init__(self, **kwargs):
                self.message = kwargs.get('message')
        fake.PageUnloadable = PageUnloadable
        with patch.dict(sys.modules, {'changedetectionio': types.ModuleType('changedetectionio'),
                                      'changedetectionio.content_fetchers': types.ModuleType('changedetectionio.content_fetchers'),
                                      'changedetectionio.content_fetchers.exceptions': fake}):
            token = _SHARED_FETCH.set(True)
            try:
                with self.assertRaises(PageUnloadable) as cm:
                    await lease.wait_for_timeout(5000)
                self.assertIn('Google verification', cm.exception.message)
            finally:
                _SHARED_FETCH.reset(token)
        self.assertEqual(p.waited, [5000])

    async def test_cloudflare_detected_before_extraction(self):
        p = FakePage('Performing security verification - Cloudflare')
        lease = _ManagedPage(p, asyncio.Semaphore(1))
        fake = types.ModuleType('changedetectionio.content_fetchers.exceptions')
        class PageUnloadable(Exception):
            def __init__(self, **kwargs):
                self.message = kwargs.get('message')
        fake.PageUnloadable = PageUnloadable
        with patch.dict(sys.modules, {'changedetectionio': types.ModuleType('changedetectionio'),
                                      'changedetectionio.content_fetchers': types.ModuleType('changedetectionio.content_fetchers'),
                                      'changedetectionio.content_fetchers.exceptions': fake}):
            token = _SHARED_FETCH.set(True)
            try:
                with self.assertRaises(PageUnloadable) as cm:
                    await lease.wait_for_timeout(5000)
                self.assertIn('Cloudflare verification', cm.exception.message)
            finally:
                _SHARED_FETCH.reset(token)

    async def test_manual_preview_wait_not_rejected(self):
        p = FakePage('Cloudflare Performing security verification')
        lease = _ManagedPage(p, asyncio.Semaphore(1))
        token = _SHARED_FETCH.set(False)
        try:
            await lease.wait_for_timeout(250)
        finally:
            _SHARED_FETCH.reset(token)
        self.assertEqual(p.waited, [250])

    async def test_normal_page_is_allowed(self):
        p = FakePage('Product Price $1499')
        lease = _ManagedPage(p, asyncio.Semaphore(1))
        token = _SHARED_FETCH.set(True)
        try:
            await lease.wait_for_timeout(250)
        finally:
            _SHARED_FETCH.reset(token)
        self.assertEqual(p.waited, [250])

    def test_google_and_cloudflare_string_recognition(self):
        self.assertEqual(challenge_kind('请进行人机身份验证', url='https://scholar.google.com.hk/'),
                         'Google verification')
        self.assertEqual(challenge_kind('Performing security verification - Cloudflare'),
                         'Cloudflare verification')
