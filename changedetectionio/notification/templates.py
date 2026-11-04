"""Small, copy-on-select notification template library.

Templates never store notification destinations and never bind to existing Watches.
"""
from uuid import uuid4

from changedetectionio.notification import (
    default_notification_body, default_notification_title, default_notification_format,
    valid_notification_formats,
)
from changedetectionio.jinja2_custom import create_jinja_env

PRODUCT_HTML = '{% if test_notification %}🧪 TEST · {% endif %}{{ watch_title|e }}\n<b>💰 {{ purchase_alert.display_price|e }}</b>{% if purchase_alert.display_change %} {{ purchase_alert.display_change|e }}{% endif %}\n📦 {{ purchase_alert.stock_text|e }}\n<a href="{{ (watch_open_url or watch_url)|e }}">🔗 View product</a>\n<blockquote expandable>🎯 {{ purchase_alert.rule_text|e }}\n🔔 {% if test_notification %}Test only — no monitoring condition asserted{% else %}{{ purchase_alert.reason_text|e }}{% endif %}{% if purchase_alert.reference_price is not none %}\n📊 Reference: {{ purchase_alert.reference_price|e }}{% endif %}</blockquote>'
PRODUCT_RICH = '{"blocks":[{"type":"heading","text":{{ (("🧪 TEST · " if test_notification else "") + (watch_title or ""))|tojson }},"size":3},{"type":"paragraph","text":{{ ("💰 " + (purchase_alert.display_price or "Unknown") + (" · " + purchase_alert.display_change if purchase_alert.display_change else ""))|tojson }}},{"type":"paragraph","text":{{ ("📦 " + (purchase_alert.stock_text or "Unknown"))|tojson }}},{"type":"paragraph","text":{{ ("🔗 " + (watch_open_url or watch_url or ""))|tojson }}},{"type":"details","summary":"Monitoring details","blocks":[{"type":"paragraph","text":{{ ("🎯 " + (purchase_alert.rule_text or "No active rule"))|tojson }}},{"type":"paragraph","text":{{ ("🔔 " + ("Test only — no monitoring condition asserted" if test_notification else (purchase_alert.reason_text or "Monitoring event")))|tojson }}},{"type":"paragraph","text":{{ ("📊 Reference: " + (purchase_alert.reference_price|string if purchase_alert.reference_price is not none else "Not available"))|tojson }}}]}]}'

PRESETS = (
    dict(id='builtin-general', name='General webpage change',
         title=default_notification_title, body=default_notification_body,
         format=default_notification_format, builtin=True),
    dict(id='builtin-product-html', name='Telegram product · HTML (foldable)',
         title='🛒 {{ watch_title }}', body=PRODUCT_HTML,
         format='telegram_html', builtin=True),
    dict(id='builtin-product-rich', name='Telegram product · Rich details',
         title='🛒 {{ watch_title }}', body=PRODUCT_RICH,
         format='telegram_rich', builtin=True),
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
    if fmt not in ('text', 'html', 'htmlcolor', 'markdown', 'telegram_html', 'telegram_markdownv2', 'telegram_rich'):
        raise ValueError('Invalid notification format')
    result['format'] = fmt
    env = create_jinja_env()
    for key in ('title', 'body'):
        env.parse(result[key])  # syntax validation; runtime uses existing sandboxed renderer
    if fmt == 'telegram_rich':
        # Validate the JSON's fixed structure with sample placeholder values at save time.
        from changedetectionio.notification.telegram_formats import validate_rich_message
        sample = {'watch_title':'Example','watch_url':'https://example.com',
                  'watch_open_url':'https://example.com','test_notification':True,
                  'purchase_alert':{'display_price':'$12.00','display_change':'',
                                    'stock_text':'In stock','rule_text':'Example',
                                    'reason_text':'Test','reference_price':None}}
        from changedetectionio.jinja2_custom import render
        validate_rich_message(render(template_str=result['body'], **sample))
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
