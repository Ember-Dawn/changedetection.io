"""Regression for localized Google Scholar and Cloudflare challenge detection."""
import unittest
from changedetection_cloak_shared.page_readiness import challenge_kind

class ChallengeStateTests(unittest.TestCase):
    def test_scholar_chinese_verification(self):
        self.assertEqual(challenge_kind('请进行人机身份验证', url='https://scholar.google.com.hk/citations?user=abc'), 'Google verification')

    def test_normal_scholar(self):
        self.assertIsNone(challenge_kind('作者的最新论文', url='https://scholar.google.com.hk/citations?user=abc'))

    def test_large_verification_document(self):
        self.assertEqual(challenge_kind('Cloudflare Performing security verification' + 'x'*30000),
                         'Cloudflare verification')

    def test_microcenter_verification(self):
        self.assertEqual(challenge_kind('Cloudflare Performing security verification'),
                         'Cloudflare verification')
