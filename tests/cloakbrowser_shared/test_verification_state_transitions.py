"""Regression: notification admission is not delivery; stale events are discarded."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import loguru
except ImportError:
    fake = types.ModuleType('loguru')
    fake.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None)
    sys.modules['loguru'] = fake
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from changedetectionio.verification_alerts import (
    mark_verification, clear_after_success, delivery_is_current, acknowledge_delivery,
)

class FakeStore:
    def __init__(self):
        self.watch = {'url': 'https://example.com'}
        self.data = {'watching': {'test': self.watch}}
    def update_watch(self, uuid, update_obj):
        self.data['watching'][uuid].update(update_obj)

class Service:
    def __init__(self, store, events, enabled=True):
        self.store = store
        self.events = events
        self.enabled = enabled
    def send_verification_state_notification(self, uuid, kind, recovered=False, token=None):
        if not self.enabled:
            return False
        self.events.append({'watch_uuid': uuid,
                            'verification_event_reason': kind,
                            'verification_event_type': 'recovery' if recovered else 'attention',
                            'verification_event_token': token})
        return True

class StateTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.events = []
        self.service = Service(self.store, self.events)
        module = types.ModuleType('changedetectionio.notification_service')
        module.create_notification_service = lambda datastore, q: self.service
        self.patcher = patch.dict(sys.modules, {'changedetectionio.notification_service': module})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_google_delivery_and_recovery(self):
        mark_verification(self.store, object(), 'test', 'Google verification')
        mark_verification(self.store, object(), 'test', 'Google verification')
        self.assertEqual(len(self.events), 1)
        self.assertIsNone(self.store.watch.get('manual_attention_notified_reason'))
        acknowledge_delivery(self.store, self.events[0], succeeded=True)
        self.assertEqual(self.store.watch['manual_attention_notified_reason'], 'Google verification')
        clear_after_success(self.store, object(), 'test')
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.events[1]['verification_event_type'], 'recovery')
        acknowledge_delivery(self.store, self.events[1], succeeded=True)
        self.assertIsNone(self.store.watch.get('manual_attention_recovery_reason'))
        self.assertIsNone(self.store.watch['manual_attention_reason'])

    def test_failed_delivery_can_retry_after_cooldown(self):
        mark_verification(self.store, object(), 'test', 'Cloudflare verification')
        first = self.events[0]
        acknowledge_delivery(self.store, first, succeeded=False)
        mark_verification(self.store, object(), 'test', 'Cloudflare verification')
        self.assertEqual(len(self.events), 1)
        self.store.watch['manual_attention_last_attempt'] = 0
        mark_verification(self.store, object(), 'test', 'Cloudflare verification')
        self.assertEqual(len(self.events), 2)
        self.assertNotEqual(first['verification_event_token'], self.events[1]['verification_event_token'])
        self.assertFalse(delivery_is_current(self.store, first))

    def test_pending_event_expires_across_process_restart(self):
        mark_verification(self.store, object(), 'test', 'Google verification')
        self.store.watch['manual_attention_pending_since'] = 1
        self.store.watch['manual_attention_last_attempt'] = 1
        mark_verification(self.store, object(), 'test', 'Google verification')
        self.assertEqual(len(self.events), 2)
        self.assertFalse(delivery_is_current(self.store, self.events[0]))

    def test_stale_alert_is_not_delivered_after_recovery(self):
        mark_verification(self.store, object(), 'test', 'Google verification')
        event = self.events[0]
        clear_after_success(self.store, object(), 'test')
        self.assertFalse(delivery_is_current(self.store, event))
        self.assertEqual(len(self.events), 1)

    def test_unavailable_channel_retries_without_cooldown(self):
        self.service.enabled = False
        mark_verification(self.store, object(), 'test', 'Cloudflare verification')
        self.assertEqual(self.events, [])
        self.service.enabled = True
        mark_verification(self.store, object(), 'test', 'Cloudflare verification')
        self.assertEqual(len(self.events), 1)

    def test_failed_recovery_retries(self):
        mark_verification(self.store, object(), 'test', 'Google verification')
        acknowledge_delivery(self.store, self.events[0], succeeded=True)
        clear_after_success(self.store, object(), 'test')
        acknowledge_delivery(self.store, self.events[1], succeeded=False)
        self.store.watch['manual_attention_recovery_last_attempt'] = 0
        clear_after_success(self.store, object(), 'test')
        self.assertEqual(len(self.events), 3)
