"""Regression checks for known verification pages and passive readiness."""
import os
import unittest
from unittest.mock import patch

from changedetection_cloak_shared.page_readiness import challenge_kind, wait_for_page_ready


class ChallengeClassifierTests(unittest.TestCase):
    def test_google_scholar_gate(self):
        text = "我们的系统检测到您的计算机网络中存在异常流量。 reCAPTCHA I'm not a robot"
        self.assertEqual(challenge_kind(text), 'Google verification')

    def test_cloudflare_interstitial(self):
        text = ('www.microcenter.com Performing security verification '
                'This website uses a security service to protect against malicious bots. Cloudflare')
        self.assertEqual(challenge_kind(text), 'Cloudflare verification')

    def test_article_mentions_cloudflare(self):
        self.assertIsNone(challenge_kind('Cloudflare improves performance for our website.'))

    def test_normal_embedded_recaptcha(self):
        self.assertIsNone(challenge_kind('<div class="g-recaptcha">Submit</div>'))

    def test_google_sorry_url(self):
        self.assertEqual(challenge_kind('reCAPTCHA', url='https://google.com/sorry'), 'Google verification')


class FakePage:
    def __init__(self, bodies):
        self._bodies = iter(bodies)

    async def evaluate(self, _script):
        return {'text': next(self._bodies), 'title': '', 'url': 'https://example.com'}


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_page(self):
        with patch.dict(os.environ, {'CLOAKBROWSER_PAGE_SETTLE_SECONDS': '0'}):
            self.assertIsNone(await wait_for_page_ready(FakePage(['Example Domain'])))

    async def test_persistent_challenge(self):
        with patch.dict(os.environ, {'CLOAKBROWSER_PAGE_SETTLE_SECONDS': '0',
                                     'CLOAKBROWSER_CHALLENGE_WAIT_SECONDS': '0'}):
            self.assertEqual(await wait_for_page_ready(
                FakePage(['Performing security verification by Cloudflare'])),
                'Cloudflare verification')
