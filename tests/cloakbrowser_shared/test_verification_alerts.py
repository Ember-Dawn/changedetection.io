"""Verification alerts use existing configured Apprise notification channels."""
import queue
import unittest
from changedetectionio.notification_service import NotificationService


class Watch(dict):
    open_link_override = None


class Store:
    def __init__(self, muted=False):
        self.watch = Watch({
            'url': 'https://example.com',
            'notification_urls': ['tgram://test-channel'],
            'notification_muted': muted,
        })
        self.data = {
            'watching': {'test-watch': self.watch},
            'settings': {'application': {
                'notification_urls': [],
                'notification_format': 'text',
                'notification_title': '',
                'notification_body': '',
            }},
        }

    def get_all_tags_for_watch(self, uuid):
        return {}


class VerificationNotificationTests(unittest.TestCase):
    def test_queue_verification_and_recovery(self):
        messages = queue.Queue()
        service = NotificationService(Store(), messages)
        self.assertTrue(service.send_verification_state_notification('test-watch', 'Cloudflare verification'))
        start = messages.get_nowait()
        self.assertIn('需要人机验证', start['notification_title'])
        self.assertTrue(service.send_verification_state_notification('test-watch', 'Cloudflare verification', recovered=True))
        finish = messages.get_nowait()
        self.assertIn('人机验证已解除', finish['notification_title'])

    def test_muted_watch_does_not_notify(self):
        messages = queue.Queue()
        service = NotificationService(Store(muted=True), messages)
        self.assertFalse(service.send_verification_state_notification('test-watch', 'Google verification'))
        self.assertTrue(messages.empty())
