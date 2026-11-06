"""Health notice lifecycle tests that do not need a running CloakBrowser."""
import importlib.util
import pathlib
import sys
import types
import unittest
from queue import Queue

PATH = pathlib.Path(__file__).resolve().parents[2] / 'changedetectionio/watch_health/alerts.py'
spec = importlib.util.spec_from_file_location('watch_health_alerts_contract', PATH)
alerts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alerts)


class Watch(dict):
    open_link_override = None


class Store:
    def __init__(self):
        self.data = {'watching': {'w': Watch(title='GPU <Pro>', url='https://shop.example/p?x=1&y=2',
                                          watch_health={'consecutive_failures': 2})}}

    def update_watch(self, uuid=None, update_obj=None, **kwargs):
        self.data['watching'][uuid].update(update_obj)


class HealthNoticeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.queue = Queue()
        self.old = sys.modules.get('changedetectionio.notification_service')
        fake = types.ModuleType('changedetectionio.notification_service')
        fake.NotificationContextData = dict
        fake._check_cascading_vars = lambda store, key, watch: ['tgram://example']
        sys.modules['changedetectionio.notification_service'] = fake

    def tearDown(self):
        if self.old is None:
            sys.modules.pop('changedetectionio.notification_service', None)
        else:
            sys.modules['changedetectionio.notification_service'] = self.old

    def test_failure_recovery_acknowledgements_share_event_id(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'HTTP error code 503')
        failed = self.queue.get_nowait()
        self.assertEqual(failed['notification_title'], '⚠️ 监控异常')
        self.assertIn('&lt;Pro&gt;', failed['notification_body'])
        self.assertIn('x=1&amp;y=2', failed['notification_body'])
        self.assertIn('HTTP 503', failed['notification_body'])
        self.assertEqual(failed['notification_format'], 'telegram_html')
        self.assertTrue(alerts.delivery_is_current(self.store, failed))
        alerts.acknowledge(self.store, failed, True)
        alerts.on_result(self.store, self.queue, 'w', 'success', 'failed', 'healthy')
        recovered = self.queue.get_nowait()
        self.assertEqual(recovered['health_failure_id'], failed['health_failure_id'])
        self.assertEqual(recovered['notification_title'], '✅ 监控已恢复')
        self.assertIn('原错误：HTTP 503', recovered['notification_body'])
        alerts.acknowledge(self.store, recovered, True)
        self.assertEqual(self.store.data['watching']['w']['watch_health_alert'], {})
        alerts.on_result(self.store, self.queue, 'w', 'success', 'healthy', 'healthy')
        self.assertTrue(self.queue.empty())

    def test_failed_delivery_cannot_generate_recovery(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'timeout')
        failed = self.queue.get_nowait()
        alerts.acknowledge(self.store, failed, False)
        alerts.on_result(self.store, self.queue, 'w', 'success', 'failed', 'healthy')
        self.assertTrue(self.queue.empty())
        self.assertEqual(self.store.data['watching']['w']['watch_health_alert'], {})

    def test_obsolete_failure_does_not_survive_success(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'timeout')
        pending = self.queue.get_nowait()
        alerts.on_result(self.store, self.queue, 'w', 'success', 'failed', 'healthy')
        self.assertFalse(alerts.delivery_is_current(self.store, pending))
        alerts.acknowledge(self.store, pending, True)
        self.assertTrue(self.queue.empty())

    def test_recognized_challenge_invalidates_generic_alert(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'timeout')
        pending = self.queue.get_nowait()
        alerts.on_result(self.store, self.queue, 'w', 'attention', 'failed', 'action_required')
        self.assertFalse(alerts.delivery_is_current(self.store, pending))


    def test_mixed_destinations_use_plaintext_without_signed_url(self):
        service = sys.modules['changedetectionio.notification_service']
        service._check_cascading_vars = lambda store, key, watch: ['tgram://example', 'mailto://hello@example.com']
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'browser https://example.com/key?private=123 failed')
        notice = self.queue.get_nowait()
        self.assertEqual(notice['notification_format'], 'text')
        self.assertIn('GPU <Pro>', notice['notification_body'])
        self.assertNotIn('private=123', notice['notification_body'])
        self.assertIn('[URL]', notice['notification_body'])

    def test_duplicate_failures_do_not_enqueue_another_incident(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'HTTP 503')
        first = self.queue.get_nowait()
        alerts.acknowledge(self.store, first, True)
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'failed', 'failed', 'HTTP 503')
        self.assertTrue(self.queue.empty())
        self.assertEqual(self.store.data['watching']['w']['watch_health_alert']['failure_id'], first['health_failure_id'])

    def test_failed_recovery_delivery_keeps_incident_until_ack(self):
        alerts.on_result(self.store, self.queue, 'w', 'failure', 'degraded', 'failed', 'HTTP 503')
        notice = self.queue.get_nowait()
        alerts.acknowledge(self.store, notice, True)
        alerts.on_result(self.store, self.queue, 'w', 'success', 'failed', 'healthy')
        recovery = self.queue.get_nowait()
        alerts.acknowledge(self.store, recovery, False)
        state = self.store.data['watching']['w']['watch_health_alert']
        self.assertFalse(state['active'])
        self.assertTrue(state['notified'])
        self.assertIsNone(state['pending'])
        # A stale acknowledgement cannot accidentally clear the incident.
        alerts.acknowledge(self.store, recovery, True)
        self.assertEqual(self.store.data['watching']['w']['watch_health_alert']['failure_id'], notice['health_failure_id'])


if __name__ == '__main__':
    unittest.main()
