"""Real NotificationService queue construction; Apprise network never invoked."""
import queue
import unittest

from changedetectionio.notification_service import NotificationService


class Watch(dict):
    open_link_override = None


class Store:
    def __init__(self, muted=False):
        self.watch = Watch({
            'uuid': 'watch-test', 'url': 'https://example.com/',
            'notification_urls': ['tgram://fake-token/fake-chat'],
            'notification_muted': muted,
        })
        self.data = {'watching': {'watch-test': self.watch},
                     'settings': {'application': {'notification_urls': [],
                                                  'notification_format': 'htmlcolor'}}}

    def get_all_tags_for_watch(self, uuid):
        return {}


class DeliveryTests(unittest.TestCase):
    def test_verification_uses_plaintext_and_valid_template(self):
        q = queue.Queue()
        service = NotificationService(Store(), q)
        self.assertTrue(service.send_verification_state_notification('watch-test', 'Cloudflare verification'))
        message = q.get_nowait()
        self.assertEqual(message['notification_format'], 'text')
        self.assertEqual(message['watch_uuid'], 'watch-test')
        self.assertIn('Cloudflare verification', message['notification_body'])
        self.assertIn('{{base_url}}manual-browser/', message['notification_body'])
        self.assertNotIn('\\n', message['notification_body'])
        self.assertFalse(q.qsize())

    def test_muted_does_not_enqueue(self):
        q = queue.Queue()
        self.assertFalse(NotificationService(Store(muted=True), q).send_verification_state_notification(
            'watch-test', 'Google verification'))
        self.assertTrue(q.empty())

    def test_recovery_title(self):
        q = queue.Queue()
        self.assertTrue(NotificationService(Store(), q).send_verification_state_notification(
            'watch-test', 'Google verification', recovered=True))
        self.assertIn('resolved', q.get_nowait()['notification_title'])
