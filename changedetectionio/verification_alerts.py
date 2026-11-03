"""Shared-browser challenge state transitions used by worker fetch outcomes.

Unknown/ordinary fetch errors never clear the manual-attention state.
Notifications are queued only once per state and can be retried when a watch
has no notification channel configured at the time of initial detection.
"""
from loguru import logger


def shared_backend(watch, datastore, fetcher=None):
    # Use the resolved fetcher when a tag/group overrides the watch setting.
    if getattr(fetcher, 'backend_name', None) == 'html_cloakbrowser_shared':
        return True
    backend = getattr(watch, 'get_fetch_backend', None)
    if backend == 'system':
        backend = datastore.data['settings']['application'].get('fetch_backend')
    return backend == 'html_cloakbrowser_shared'


def classify_fetcher(fetcher, watch):
    if fetcher is None:
        return None
    from changedetection_cloak_shared.page_readiness import challenge_kind
    return challenge_kind(getattr(fetcher, 'content', None),
                          url=getattr(watch, 'link', None) or watch.get('url', ''))


def mark_verification(datastore, notification_q, uuid, kind):
    watch = datastore.data['watching'].get(uuid)
    if not watch or not kind:
        return
    if watch.get('manual_attention_reason') != kind:
        datastore.update_watch(uuid, {'manual_attention_reason': kind,
                                      'manual_attention_notified_reason': None})
    if watch.get('manual_attention_notified_reason') == kind:
        return
    try:
        from changedetectionio.notification_service import create_notification_service
        queued = create_notification_service(datastore, notification_q).send_verification_state_notification(uuid, kind)
    except Exception as exc:
        logger.warning('Could not queue verification alert for {}: {}', uuid, exc)
        return
    if queued:
        datastore.update_watch(uuid, {'manual_attention_notified_reason': kind})
    else:
        logger.info('Verification for {} recorded; no enabled notification URL configured', uuid)


def clear_after_success(datastore, notification_q, uuid):
    watch = datastore.data['watching'].get(uuid)
    if not watch or not watch.get('manual_attention_reason'):
        return
    reason = watch.get('manual_attention_reason')
    had_queued_alert = watch.get('manual_attention_notified_reason') == reason
    # Clear state only when normal fetch+processing succeeded, not on errors.
    datastore.update_watch(uuid, {'manual_attention_reason': None,
                                  'manual_attention_notified_reason': None})
    if had_queued_alert:
        try:
            from changedetectionio.notification_service import create_notification_service
            create_notification_service(datastore, notification_q).send_verification_state_notification(uuid, reason, recovered=True)
        except Exception as exc:
            logger.warning('Could not queue verification recovery for {}: {}', uuid, exc)
