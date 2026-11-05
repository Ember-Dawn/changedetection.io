"""Persisted, delivery-acknowledged product rule failure/recovery notifications."""
import secrets
import time
from html import escape


_RETRY_SECONDS = 300
_PENDING_TIMEOUT = 600


def _state(watch):
    return dict(watch.get('product_rule_alert_state') or {})


def _put(datastore, uuid, state):
    datastore.update_watch(uuid=uuid, update_obj={'product_rule_alert_state': state})


def _enqueue(datastore, queue, uuid, state, event):
    from changedetectionio.notification_service import NotificationContextData, _check_cascading_vars
    watch = datastore.data['watching'].get(uuid)
    if not watch or watch.get('notification_muted') or not queue:
        return False
    urls = _check_cascading_vars(datastore, 'notification_urls', watch)
    if not urls:
        return False
    now = time.time()
    if state.get('pending') and now - float(state.get('pending_since') or 0) < _PENDING_TIMEOUT:
        return False
    if now - float(state.get('last_attempt') or 0) < _RETRY_SECONDS:
        return False
    token = secrets.token_urlsafe(16)
    state.update(pending=token, pending_since=now, last_attempt=now, pending_event=event)
    _put(datastore, uuid, state)
    link = watch.open_link_override or watch.get('url') or ''
    title = watch.get('title') or watch.get('page_title') or link
    rule_id = state.get('rule_id') or 'Selected rule'
    all_telegram = all(str(url).startswith('tgram://') for url in urls)
    if event == 'failure':
        headline = '⚠️ 商品解析失败'
        explanation = (state.get('reason') or 'Rule extraction failed')[:400]
    else:
        headline = '✅ 商品解析已恢复'
        explanation = ''
    if all_telegram:
        body = '<a href="{}">{}</a>\n规则：{}'.format(escape(link, quote=True), escape(title), escape(rule_id))
        if explanation:
            body += '\n原因：' + escape(explanation)
        fmt = 'telegram_html'
    else:
        body = '{}\n{}\n规则：{}'.format(title, link, rule_id)
        if explanation:
            body += '\n原因：' + explanation
        fmt = 'text'
    context = NotificationContextData({
        'uuid': uuid, 'watch_uuid': uuid, 'watch_url': watch.get('url'),
        'watch_open_url': link, 'notification_urls': urls,
        'notification_title': headline, 'notification_body': body,
        'notification_format': fmt, 'screenshot': None,
        'product_rule_event': event, 'product_rule_token': token,
    })
    try:
        queue.put(context)
    except Exception:
        state.update(pending=None, pending_since=0, last_attempt=0)
        _put(datastore, uuid, state)
        raise
    return True


def failure(datastore, queue, uuid, reason):
    watch = datastore.data['watching'].get(uuid)
    if not watch or watch.get('processor') != 'restock_diff':
        return
    state = _state(watch)
    if not state.get('failed'):
        state = {'failed': True, 'notified': False, 'reason': str(reason)[:400],
                 'rule_id': _selected_rule_id(watch), 'pending': None,
                 'last_attempt': 0}
        _put(datastore, uuid, state)
    if not state.get('notified'):
        _enqueue(datastore, queue, uuid, state, 'failure')


def recovered(datastore, queue, uuid):
    watch = datastore.data['watching'].get(uuid)
    if not watch:
        return
    state = _state(watch)
    if state.get('failed'):
        if not state.get('notified'):
            _put(datastore, uuid, {})
            return
        state.update(failed=False, pending=None, last_attempt=0)
        _put(datastore, uuid, state)
    if state and not state.get('failed') and state.get('notified'):
        _enqueue(datastore, queue, uuid, state, 'recovery')


def _selected_rule_id(watch):
    try:
        import json
        from pathlib import Path
        file = Path(watch.data_dir) / 'restock_diff.json'
        return (json.loads(file.read_text(encoding='utf-8')).get('restock_diff') or {}).get('extraction_rule_id') or ''
    except (OSError, ValueError, TypeError):
        return ''


def delivery_is_current(datastore, context):
    event = context.get('product_rule_event')
    if not event:
        return True
    watch = datastore.data['watching'].get(context.get('watch_uuid'))
    if not watch:
        return False
    state = _state(watch)
    return (state.get('pending_event') == event and
            state.get('pending') == context.get('product_rule_token') and
            bool(state.get('failed')) == (event == 'failure'))


def acknowledge(datastore, context, succeeded):
    if not context.get('product_rule_event') or not delivery_is_current(datastore, context):
        return
    uuid = context['watch_uuid']
    state = _state(datastore.data['watching'][uuid])
    event = context['product_rule_event']
    state.update(pending=None, pending_since=0)
    if succeeded:
        if event == 'failure':
            state['notified'] = True
        else:
            state = {}
    _put(datastore, uuid, state)
