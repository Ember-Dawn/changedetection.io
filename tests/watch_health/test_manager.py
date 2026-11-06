"""Watch Health contract tests: independent of browser and Telegram transports."""
import time

from changedetectionio.watch_health.manager import policy, record_result, retry_due
from changedetectionio.watch_health.alerts import on_result


class FakeStore:
    def __init__(self, **watch_config):
        self.data = {
            'settings': {'requests': {}, 'application': {'fetch_backend': 'html_cloakbrowser_shared'}},
            'watching': {'w': {'uuid': 'w', 'url': 'https://example.org/product',
                              'processor': 'restock_diff', **watch_config}},
        }

    def update_watch(self, uuid=None, update_obj=None):
        self.data['watching'][uuid].update(update_obj)


def test_defaults_overrides_and_bounds():
    store = FakeStore()
    assert policy(store, store.data['watching']['w'])['reliability_retry_minutes'] == 5
    store.data['settings']['requests']['reliability_retry_minutes'] = 12
    assert policy(store, store.data['watching']['w'])['reliability_retry_minutes'] == 12
    store.data['watching']['w'].update(reliability_use_default=False,
                                       reliability_retry_minutes=3,
                                       reliability_page_attempts=99)
    opts = policy(store, store.data['watching']['w'])
    assert opts['reliability_retry_minutes'] == 3
    assert opts['reliability_page_attempts'] == 3


def test_two_failed_full_checks_then_recovery():
    store = FakeStore()
    first = record_result(store, 'w', 'failure', reason='price unavailable', now=1000)
    assert first == ('unknown', 'degraded')
    assert not retry_due(store.data['watching']['w'], now=1299)
    assert retry_due(store.data['watching']['w'], now=1300)
    second = record_result(store, 'w', 'failure', reason='price unavailable', now=1300)
    assert second == ('degraded', 'failed')
    watch = store.data['watching']['w']
    assert watch['watch_health']['consecutive_failures'] == 2
    third = record_result(store, 'w', 'success', now=1400)
    assert third == ('failed', 'healthy')
    assert watch['watch_health']['consecutive_failures'] == 0
    assert watch['watch_health']['next_retry_at'] == 0


def test_verification_skips_accelerated_rechecks():
    store = FakeStore()
    record_result(store, 'w', 'failure', now=1000)
    result = record_result(store, 'w', 'attention', reason='Cloudflare verification', now=1200)
    assert result == ('degraded', 'action_required')
    assert not retry_due(store.data['watching']['w'], now=999999)
    assert record_result(store, 'w', 'success', now=1300) == ('action_required', 'healthy')


def test_disable_acceleration_and_durable_state():
    store = FakeStore(reliability_use_default=False, reliability_retry_minutes=0)
    record_result(store, 'w', 'failure', now=1000)
    assert store.data['watching']['w']['watch_health']['next_retry_at'] == 0
    assert not retry_due(store.data['watching']['w'], now=1e9)
