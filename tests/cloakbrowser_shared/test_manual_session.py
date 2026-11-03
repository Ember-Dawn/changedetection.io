"""Unit tests for shared manual-session admission without a real Chromium."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manual_session import ManualSessionManager, ManualSessionError
from changedetection_cloak_shared.page_readiness import challenge_kind


class ManualReservations(unittest.TestCase):
    def test_only_one_manual_session_can_open(self):
        manual = ManualSessionManager()
        manual._reserve('watch-one')
        self.assertTrue(manual.is_reserved('watch-one'))
        with self.assertRaises(ManualSessionError):
            manual._reserve('watch-two')
        manual._unreserve('watch-one')
        self.assertFalse(manual.is_reserved('watch-one'))
        manual._reserve('watch-two')
        manual._unreserve('watch-two')

    def test_manual_session_protects_existing_watch_pause(self):
        # Reservation is a transient in-memory lock, not a datastore write.
        manual = ManualSessionManager()
        manual._reserve('paused-watch')
        self.assertEqual(manual._reserved, {'paused-watch'})
        manual._unreserve('paused-watch')
        self.assertFalse(manual._reserved)


class LocalizedVerification(unittest.TestCase):
    def test_google_scholar_chinese_interstitial(self):
        text = 'Google 学术搜索 请进行人机身份验证 进行人机身份验证'
        self.assertEqual(challenge_kind(text, url='https://scholar.google.com.hk/citations?user=abc'),
                         'Google verification')

    def test_normal_google_scholar_page(self):
        text = 'Google Scholar citations Articles Cited by Title Year'
        self.assertIsNone(challenge_kind(text, url='https://scholar.google.com.hk/citations?user=abc'))


if __name__ == '__main__':
    unittest.main()
