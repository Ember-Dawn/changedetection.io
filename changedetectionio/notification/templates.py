"""Small, copy-on-select notification template library.

Templates never store notification destinations and never bind to existing Watches.
"""
from uuid import uuid4

from changedetectionio.notification import (
    default_notification_body, default_notification_title, default_notification_format,
    valid_notification_formats,
)
from changedetectionio.jinja2_custom import create_jinja_env

PRESETS = (
    dict(id='builtin-general', name='General webpage change',
         title=default_notification_title, body=default_notification_body,
         format=default_notification_format, builtin=True),
    dict(id='builtin-product', name='Product price and stock',
         title='Product alert: {{ restock.title or watch_title or watch_url }}',
         body=('Product: {{ restock.title or watch_title or watch_url }}\n'
               'Price: {{ restock.price }} {{ restock.currency or "" }}\n'
               'Stock: {{ purchase_alert.stock_text }}\n'
               'Rule: {{ purchase_alert.rule_text }}\n'
               'Triggered: {{ purchase_alert.reason_text }}\n'
               '{% if purchase_alert.reference_price is not none %}'
               'Reference price: {{ purchase_alert.reference_price }}\n{% endif %}'
               '{% if purchase_alert.price_change_amount is not none %}'
               'Price change: {{ purchase_alert.price_change_amount }}'
               ' ({{ purchase_alert.percent_change }}%)\n{% endif %}'
               'Link: {{ watch_open_url or watch_url }}'),
         format='text', builtin=True),
    dict(id='builtin-compact', name='Compact change alert',
         title='Watch alert: {{ watch_title or watch_url }}',
         body='{{ watch_title or watch_url }}\n{{ diff }}\n{{ watch_open_url or watch_url }}',
         format='text', builtin=True),
)
MAX_TEMPLATES = 50


def validate_template(item):
    if not isinstance(item, dict):
        raise ValueError('Invalid template')
    result = {}
    for key, limit in (('name', 100), ('title', 2000), ('body', 20000)):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('Invalid template ' + key)
        result[key] = value.strip() if key == 'name' else value
    fmt = item.get('format', 'text')
    if fmt not in ('text', 'html', 'htmlcolor', 'markdown'):
        raise ValueError('Invalid notification format')
    result['format'] = fmt
    env = create_jinja_env()
    for key in ('title', 'body'):
        env.parse(result[key])  # syntax validation; runtime uses existing sandboxed renderer
    return result


def get_templates(datastore):
    stored = datastore.data['settings']['application'].get('notification_templates') or []
    return [dict(item) for item in PRESETS] + [dict(item) for item in stored if isinstance(item, dict)]


def mutate_templates(datastore, action, item):
    app = datastore.data['settings']['application']
    stored = list(app.get('notification_templates') or [])
    item_id = item.get('id') if isinstance(item, dict) else None
    if action == 'delete':
        if not isinstance(item_id, str) or not any(t.get('id') == item_id for t in stored):
            raise ValueError('Unknown custom template')
        stored = [t for t in stored if t.get('id') != item_id]
        result = None
    elif action in ('create', 'update'):
        validated = validate_template(item)
        if action == 'create':
            if len(stored) >= MAX_TEMPLATES:
                raise ValueError('Custom template limit reached')
            validated['id'] = 'custom-' + uuid4().hex
            stored.append(validated)
        else:
            if not isinstance(item_id, str) or not any(t.get('id') == item_id for t in stored):
                raise ValueError('Unknown custom template')
            validated['id'] = item_id
            stored = [validated if t.get('id') == item_id else t for t in stored]
        result = validated
    else:
        raise ValueError('Unknown template operation')
    app['notification_templates'] = stored
    datastore.commit()
    return result
