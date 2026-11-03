"""Manual browser recovery and navigation regression tests."""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manual_session import ManualSessionManager, ManualSessionError
from changedetection_cloak_shared.manager import manager


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.sessions = ManualSessionManager()
        self.entry = SimpleNamespace(
            token='first-token', owner='account-a', watch_uuid='watch-1',
            browser_generation=manager._generation, lease=None,
            page=SimpleNamespace(url='https://example.com/'),
            address='https://example.com/', last_active=time.monotonic(), closed=False,
        )
        self.sessions._session = self.entry

    def test_same_login_can_recover(self):
        d = self.sessions.inspect('account-a')
        self.assertTrue(d['active'])
        self.assertTrue(d['owned'])
        self.assertEqual(d['session'], 'first-token')
        self.assertEqual(d['watch_uuid'], 'watch-1')

    def test_other_login_does_not_receive_sensitive_url_or_token(self):
        d = self.sessions.inspect('account-b')
        self.assertTrue(d['active'])
        self.assertFalse(d['owned'])
        self.assertNotIn('session', d)
        self.assertNotIn('url', d)

    def test_expired_session_cannot_be_recovered(self):
        self.entry.last_active -= 1000
        d = self.sessions.inspect('account-a')
        self.assertFalse(d['active'])


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_rotates_token(self):
        s = ManualSessionManager()
        s._session = SimpleNamespace(
            token='old', owner='account-a', watch_uuid=None,
            browser_generation=manager._generation, lease=None,
            page=SimpleNamespace(url='https://example.com/'),
            address='https://example.com/', last_active=time.monotonic(), closed=False,
        )
        d = await s._resume_owned('old','account-a')
        self.assertNotEqual(d['session'], 'old')
        with self.assertRaises(ManualSessionError):
            s._get('old','account-a')
        self.assertEqual(s._get(d['session'],'account-a'),s._session)

    async def test_navigate_same_page(self):
        s = ManualSessionManager()
        page=SimpleNamespace(url='https://example.com/',goto=AsyncMock())
        s._session=SimpleNamespace(
            token='token',owner='account-a',watch_uuid=None,
            browser_generation=manager._generation,lease=None,page=page,
            address=page.url,last_active=time.monotonic(),closed=False,
        )
        with patch('changedetectionio.validate_url.is_fetch_url_allowed',return_value=(True,'')):
            await s._action('token','account-a','navigate',{'url':'https://example.com/page'})
        page.goto.assert_awaited_once_with('https://example.com/page',
                                            wait_until='domcontentloaded',timeout=35000)

    async def test_refuse_non_http_navigation(self):
        s=ManualSessionManager()
        page=SimpleNamespace(url='https://example.com/',goto=AsyncMock())
        s._session=SimpleNamespace(
            token='token',owner='account-a',watch_uuid=None,
            browser_generation=manager._generation,lease=None,page=page,
            address=page.url,last_active=time.monotonic(),closed=False,
        )
        with self.assertRaises(ManualSessionError):
            await s._action('token','account-a','navigate',{'url':'file:///etc/passwd'})
        page.goto.assert_not_awaited()
