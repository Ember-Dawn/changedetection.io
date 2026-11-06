"""Persistent, transport-acknowledged Watch Health notifications."""
import secrets
import time

RETRY_SECONDS = 300
PENDING_TIMEOUT = 600

def _put(datastore, uuid, state):
    datastore.update_watch(uuid=uuid, update_obj={'watch_health_alert': state})

def enqueue(datastore, queue, uuid, event, reason=''):
    from changedetectionio.notification_service import _check_cascading_vars, NotificationContextData
    watch = datastore.data['watching'].get(uuid)
    if watch is None or not queue or watch.get('notification_muted'):
        return False
    urls = _check_cascading_vars(datastore, 'notification_urls', watch)
    if not urls:
        return False
    state = dict(watch.get('watch_health_alert') or {})
    now = time.time()
    if state.get('pending') and now - float(state.get('pending_since') or 0) < PENDING_TIMEOUT:
        return False
    if now - float(state.get('last_attempt') or 0) < RETRY_SECONDS:
        return False
    token = secrets.token_urlsafe(16)
    state.update(pending=token, pending_since=now, last_attempt=now, event=event)
    _put(datastore, uuid, state)
    title = ('changedetection.io - Watch recovered' if event == 'recovery' else
             'changedetection.io - Watch checks failing')
    body = (('Monitoring has resumed after a confirmed failure.' if event == 'recovery' else
             'Repeated monitoring checks failed: ' + str(reason)[:400]) +
            '\nWatch: {{watch_url}}')
    try:
        queue.put(NotificationContextData({
            'notification_urls': urls, 'notification_title': title,
            'notification_body': body, 'notification_format': 'text',
            'uuid': uuid, 'watch_uuid': uuid, 'watch_url': watch.get('url'),
            'watch_open_url': watch.open_link_override or watch.get('url'),
            'health_alert_event': event, 'health_alert_token': token,
            'screenshot': None,
        }))
    except Exception:
        state.update(pending=None, pending_since=0, last_attempt=0)
        _put(datastore, uuid, state)
        raise
    return True

def on_result(datastore, queue, uuid, result, old_status, new_status, reason=''):
    if result == 'attention':
        # A recognized challenge has a dedicated, human-action notifier.
        # Invalidate old generic notices rather than delivering both kinds.
        _put(datastore, uuid, {})
        return
    watch = datastore.data['watching'].get(uuid)
    if watch is None:
        return
    state = dict(watch.get('watch_health_alert') or {})
    if result == 'failure':
        if new_status != 'failed':
            return
        if not state.get('active'):
            state = dict(active=True, notified=False, pending=None, last_attempt=0)
            _put(datastore, uuid, state)
        if not state.get('notified'):
            enqueue(datastore, queue, uuid, 'failure', reason)
    elif result == 'success':
        if state.get('active'):
            if not state.get('notified'):
                _put(datastore, uuid, {})
                return
            state.update(active=False, pending=None, last_attempt=0)
            _put(datastore, uuid, state)
        if state and not state.get('active') and state.get('notified'):
            enqueue(datastore, queue, uuid, 'recovery')

def delivery_is_current(datastore, context):
    event = context.get('health_alert_event')
    if not event:
        return True
    watch = datastore.data['watching'].get(context.get('watch_uuid'))
    if watch is None:
        return False
    state = watch.get('watch_health_alert') or {}
    return bool(state.get('pending') and state.get('pending') == context.get('health_alert_token') and
                state.get('event') == event and bool(state.get('active')) == (event == 'failure'))

def acknowledge(datastore, context, succeeded):
    if not context.get('health_alert_event') or not delivery_is_current(datastore, context):
        return
    uuid = context['watch_uuid']
    state = dict(datastore.data['watching'][uuid].get('watch_health_alert') or {})
    event = context['health_alert_event']
    state.update(pending=None, pending_since=0)
    if succeeded:
        if event == 'failure':
            state['notified'] = True
        else:
            state = {}
    _put(datastore, uuid, state)
