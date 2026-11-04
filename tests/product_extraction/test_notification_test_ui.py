"""Static regression for single-Watch test notification visibility."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
class NotificationTestUI(unittest.TestCase):
    def test_watch_has_test_button_even_when_own_recipient_empty(self):
        js=(ROOT/'changedetectionio/static/js/notifications.js').read_text()
        self.assertIn('isWatchEditor || notificationLines().length > 0',js)
    def test_tag_field_matches_normal_notification_channel(self):
        source=(ROOT/'changedetectionio/blueprint/ui/notification.py').read_text()
        self.assertIn("tag.get('notification_urls')",source)
        self.assertNotIn("tag.get('notifications_urls')",source)
