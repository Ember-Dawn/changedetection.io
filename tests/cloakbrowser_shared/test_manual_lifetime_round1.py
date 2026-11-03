"""Human operator sessions keep one supervisor across token rotations."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared'))
from changedetection_cloak_shared.manual_session import ManualSessionManager
from changedetection_cloak_shared.manager import manager

class LifetimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_does_not_create_supervisor(self):
        sessions = ManualSessionManager()
        entry = SimpleNamespace(token='original', owner='operator',
                                browser_generation=manager._generation,
                                last_active=time.monotonic(), closed=False)
        sessions._session = entry
        with patch.object(manager, 'session_alive', return_value=True):
            before = len(sessions._expiry_tasks)
            result = await sessions._resume_owned('original', 'operator')
            self.assertNotEqual(result['session'], 'original')
            self.assertEqual(len(sessions._expiry_tasks), before)

    async def test_expiry_survives_token_rotation(self):
        sessions = ManualSessionManager()
        entry = SimpleNamespace(token='original', owner='operator',
                                browser_generation=manager._generation,
                                last_active=time.monotonic()-1000, closed=False)
        sessions._session = entry
        disposed=[]
        async def dispose(token):
            disposed.append(token)
        with patch.object(manager, 'session_alive', return_value=True), \
             patch.object(sessions, '_dispose', side_effect=dispose), \
             patch('changedetection_cloak_shared.manual_session.asyncio.sleep', new=__import__('unittest').mock.AsyncMock()):
            # No need for a real browser; the same session remains current.
            entry.token='rotated'
            await sessions._expiry_watch(entry)
        self.assertEqual(disposed, ['rotated'])
