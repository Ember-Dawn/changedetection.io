"""Shared-browser challenge state transitions used by worker fetch outcomes.

Unknown/ordinary fetch errors never clear the manual-attention state.
Notifications are deduplicated while queued or confirmed as delivered, with
finite retries after transport failures and across process restarts.
"""
import secrets
import time

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


# Delivery acknowledgement is separate from queue admission. A temporary
# transport failure must not permanently silence an affected watch.
_RETRY_SECONDS = 300
_PENDING_TIMEOUT_SECONDS = 600


def _notify(datastore, notification_q, uuid, kind, *, recovered, token):
    from changedetectionio.notification_service import create_notification_service
    return bool(create_notification_service(datastore, notification_q).send_verification_state_notification(
        uuid, kind, recovered=recovered, token=token))


def classify_verification_error(error):
    """Translate only known shared-fetcher verification exceptions."""
    detail = str(getattr(error, 'message', '') or '')
    for kind in ('Google verification', 'Cloudflare verification'):
        if f'{kind} still displayed' in detail:
            return kind
    return None


def mark_verification(datastore, notification_q, uuid, kind):
    watch = datastore.data['watching'].get(uuid)
    if not watch or not kind:
        return
    if watch.get('manual_attention_reason') != kind:
        datastore.update_watch(uuid, {
            'manual_attention_reason': kind,
            'manual_attention_notified_reason': None,
            'manual_attention_pending_token': None,
            'manual_attention_pending_since': 0,
            'manual_attention_last_attempt': 0,
            # An earlier recovery is no longer meaningful for this watch.
            'manual_attention_recovery_reason': None,
            'manual_attention_recovery_pending_token': None,
        })
        watch = datastore.data['watching'].get(uuid)
    if watch.get('manual_attention_notified_reason') == kind:
        return
    if watch.get('manual_attention_pending_token'):
        if time.time() - float(watch.get('manual_attention_pending_since') or 0) < _PENDING_TIMEOUT_SECONDS:
            return
        logger.warning('Verification notification pending too long for {}; retrying', uuid)
        datastore.update_watch(uuid, {'manual_attention_pending_token': None})
    if time.time() - float(watch.get('manual_attention_last_attempt') or 0) < _RETRY_SECONDS:
        return
    token = secrets.token_urlsafe(16)
    datastore.update_watch(uuid, {'manual_attention_pending_token': token,
                                  'manual_attention_pending_since': time.time(),
                                  'manual_attention_last_attempt': time.time()})
    try:
        queued = _notify(datastore, notification_q, uuid, kind, recovered=False, token=token)
    except Exception as exc:
        logger.warning('Could not queue verification alert for {}: {}', uuid, exc)
        queued = False
    if not queued:
        # Do not start a cooldown just because no notification URL is configured.
        datastore.update_watch(uuid, {'manual_attention_pending_token': None,
                                      'manual_attention_pending_since': 0,
                                      'manual_attention_last_attempt': 0})


def _queue_recovery(datastore, notification_q, uuid):
    watch = datastore.data['watching'].get(uuid)
    if not watch:
        return
    kind = watch.get('manual_attention_recovery_reason')
    if not kind:
        return
    if watch.get('manual_attention_recovery_pending_token'):
        if time.time() - float(watch.get('manual_attention_recovery_pending_since') or 0) < _PENDING_TIMEOUT_SECONDS:
            return
        logger.warning('Recovery notification pending too long for {}; retrying', uuid)
        datastore.update_watch(uuid, {'manual_attention_recovery_pending_token': None})
    if time.time() - float(watch.get('manual_attention_recovery_last_attempt') or 0) < _RETRY_SECONDS:
        return
    token = secrets.token_urlsafe(16)
    datastore.update_watch(uuid, {'manual_attention_recovery_pending_token': token,
                                  'manual_attention_recovery_pending_since': time.time(),
                                  'manual_attention_recovery_last_attempt': time.time()})
    try:
        queued = _notify(datastore, notification_q, uuid, kind, recovered=True, token=token)
    except Exception as exc:
        logger.warning('Could not queue verification recovery for {}: {}', uuid, exc)
        queued = False
    if not queued:
        datastore.update_watch(uuid, {'manual_attention_recovery_pending_token': None,
                                      'manual_attention_recovery_pending_since': 0,
                                      'manual_attention_recovery_last_attempt': 0})


def clear_after_success(datastore, notification_q, uuid):
    watch = datastore.data['watching'].get(uuid)
    if not watch:
        return
    reason = watch.get('manual_attention_reason')
    if reason:
        had_delivered_alert = watch.get('manual_attention_notified_reason') == reason
        datastore.update_watch(uuid, {
            'manual_attention_reason': None,
            'manual_attention_notified_reason': None,
            'manual_attention_pending_token': None,
            'manual_attention_pending_since': 0,
            'manual_attention_last_attempt': 0,
            'manual_attention_recovery_reason': reason if had_delivered_alert else None,
            'manual_attention_recovery_pending_token': None,
            'manual_attention_recovery_pending_since': 0,
            'manual_attention_recovery_last_attempt': 0,
        })
    _queue_recovery(datastore, notification_q, uuid)


def delivery_is_current(datastore, context):
    """Avoid sending an obsolete alert after its watch has recovered."""
    event = context.get('verification_event_type')
    if not event:
        return True
    watch = datastore.data['watching'].get(context.get('watch_uuid') or context.get('uuid'))
    if not watch:
        return False
    token = context.get('verification_event_token')
    if event == 'attention':
        return (watch.get('manual_attention_reason') == context.get('verification_event_reason')
                and watch.get('manual_attention_pending_token') == token and token is not None)
    if event == 'recovery':
        return (not watch.get('manual_attention_reason')
                and watch.get('manual_attention_recovery_reason') == context.get('verification_event_reason')
                and watch.get('manual_attention_recovery_pending_token') == token and token is not None)
    return False


def acknowledge_delivery(datastore, context, *, succeeded):
    event = context.get('verification_event_type')
    if not event or not delivery_is_current(datastore, context):
        return
    uuid = context.get('watch_uuid') or context.get('uuid')
    if event == 'attention':
        updates = {'manual_attention_pending_token': None,
                   'manual_attention_pending_since': 0}
        if succeeded:
            updates['manual_attention_notified_reason'] = context['verification_event_reason']
        datastore.update_watch(uuid, updates)
    elif event == 'recovery':
        updates = {'manual_attention_recovery_pending_token': None,
                   'manual_attention_recovery_pending_since': 0}
        if succeeded:
            updates.update({'manual_attention_recovery_reason': None,
                            'manual_attention_recovery_last_attempt': 0})
        datastore.update_watch(uuid, updates)
