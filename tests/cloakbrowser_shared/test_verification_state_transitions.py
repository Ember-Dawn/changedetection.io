"""State transitions: first alert, repeated verification, recovery, and mute."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import loguru
except ImportError:
    loguru = types.ModuleType('loguru')
    loguru.logger = types.SimpleNamespace(info=lambda *a, **kw: None,
                                          warning=lambda *a, **kw: None)
    sys.modules['loguru'] = loguru

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from changedetectionio.verification_alerts import mark_verification, clear_after_success


class FakeStore:
    def __init__(self):
        self.watch = {'url': 'https://example.com'}
        self.data = {'watching': {'test': self.watch}}
        self.notifications = []
    def update_watch(self, uuid, update_obj):
        self.data['watching'][uuid].update(update_obj)


class Service:
    def __init__(self, calls, enabled=True):
        self.calls = calls
        self.enabled = enabled
    def send_verification_state_notification(self, uuid, kind, recovered=False):
        if not self.enabled:
            return False
        self.calls.append((uuid, kind, recovered))
        return True


class StateTests(unittest.TestCase):
    def run_scenario(self, enabled=True):
        store = FakeStore()
        calls = []
        service = Service(calls, enabled)
        module = types.ModuleType('changedetectionio.notification_service')
        module.create_notification_service = lambda datastore, q: service
        with patch.dict(sys.modules, {'changedetectionio.notification_service': module}):
            mark_verification(store, object(), 'test', 'Google verification')
            mark_verification(store, object(), 'test', 'Google verification')
            if not enabled:
                service.enabled = True
                mark_verification(store, object(), 'test', 'Google verification')
            clear_after_success(store, object(), 'test')
        return store, calls
    def test_one_alert_one_recovery(self):
        store, calls = self.run_scenario()
        self.assertEqual(calls, [('test', 'Google verification', False),
                                 ('test', 'Google verification', True)])
        self.assertIsNone(store.watch['manual_attention_reason'])
    def test_retry_alert_when_channel_becomes_available(self):
        store, calls = self.run_scenario(enabled=False)
        self.assertEqual(len(calls), 2)
    def test_cloudflare_dedup(self):
        store = FakeStore()
        calls = []
        module = types.ModuleType('changedetectionio.notification_service')
        module.create_notification_service = lambda datastore, q: Service(calls)
        with patch.dict(sys.modules, {'changedetectionio.notification_service': module}):
            mark_verification(store, object(), 'test', 'Cloudflare verification')
            mark_verification(store, object(), 'test', 'Cloudflare verification')
        self.assertEqual(calls, [('test', 'Cloudflare verification', False)])
