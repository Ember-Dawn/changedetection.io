"""Unit tests for shared manual-session admission without a real Chromium."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

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


class AdminTermination(unittest.TestCase):
    def test_stale_admin_confirmation_cannot_close_new_session(self):
        manual = ManualSessionManager()
        entry = SimpleNamespace(admin_id='new-session', closed=False)
        manual._session = entry
        with self.assertRaises(ManualSessionError):
            asyncio.run(manual._terminate_admin('stale-session'))
        self.assertIs(manual._session, entry)
        self.assertFalse(entry.closed)

    def test_admin_termination_releases_page_without_recheck(self):
        manual = ManualSessionManager()
        lease = SimpleNamespace(close=AsyncMock())
        entry = SimpleNamespace(admin_id='session-one', token='private-token',
                                closed=False, screencast=None, screencast_id='',
                                lease=lease, watch_uuid='watch-a')
        manual._session = entry
        manual._reserved.add('watch-a')
        result = asyncio.run(manual._terminate_admin('session-one'))
        self.assertEqual(result, 'watch-a')
        self.assertTrue(entry.closed)
        self.assertIsNone(manual._session)
        self.assertNotIn('watch-a', manual._reserved)
        lease.close.assert_awaited_once()

    def test_admin_snapshot_never_contains_owner_token(self):
        manual = ManualSessionManager()
        manual._session = SimpleNamespace(admin_id='public-id', token='secret',
                                          closed=False, last_active=time.monotonic())
        snapshot = manual.admin_snapshot()
        self.assertTrue(snapshot['active'])
        self.assertEqual(snapshot['admin_id'], 'public-id')
        self.assertNotIn('token', snapshot)
        self.assertNotIn('owner', snapshot)



if __name__ == '__main__':
    unittest.main()
