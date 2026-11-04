"""Small, copy-on-select notification template library.

Templates never store notification destinations and never bind to existing Watches.
"""
from uuid import uuid4

from changedetectionio.notification import (
    default_notification_body, default_notification_title, default_notification_format,
    valid_notification_formats,
)
from changedetectionio.jinja2_custom import create_jinja_env

PRODUCT_HTML = '<a href="{{ (watch_open_url or watch_url)|e }}"><b>{{ watch_title|e }}</b></a>\n{% if purchase_alert.show_price %}💰 {{ purchase_alert.display_price|e }}{% if purchase_alert.display_change and not test_notification %} {{ purchase_alert.display_change|e }}{% endif %}\n{% endif %}{% if purchase_alert.show_stock %}{{ (purchase_alert.display_stock_current if test_notification else purchase_alert.display_stock)|e }}\n{% endif %}<blockquote expandable>🎯 {{ purchase_alert.rule_text|e }}\n🔔 {% if test_notification %}Test notification — no monitoring condition asserted{% else %}{{ purchase_alert.reason_text|e }}{% endif %}{% if purchase_alert.display_reference_price and not test_notification %}\n📊 Reference: {{ purchase_alert.display_reference_price|e }}{% endif %}</blockquote>'
PRODUCT_HTML_EXPANDED = '<a href="{{ (watch_open_url or watch_url)|e }}"><b>{{ watch_title|e }}</b></a>\n{% if purchase_alert.show_price %}💰 {{ purchase_alert.display_price|e }}{% if purchase_alert.display_change and not test_notification %} {{ purchase_alert.display_change|e }}{% endif %}\n{% endif %}{% if purchase_alert.show_stock %}{{ (purchase_alert.display_stock_current if test_notification else purchase_alert.display_stock)|e }}\n{% endif %}🎯 {{ purchase_alert.rule_text|e }}\n🔔 {% if test_notification %}Test notification — no monitoring condition asserted{% else %}{{ purchase_alert.reason_text|e }}{% endif %}{% if purchase_alert.display_reference_price and not test_notification %}\n📊 Reference: {{ purchase_alert.display_reference_price|e }}{% endif %}'
PRODUCT_HTML_COMPACT = '<a href="{{ (watch_open_url or watch_url)|e }}"><b>{{ watch_title|e }}</b></a>\n{% if purchase_alert.show_price %}💰 {{ purchase_alert.display_price|e }}{% if purchase_alert.display_change and not test_notification %} {{ purchase_alert.display_change|e }}{% endif %}\n{% endif %}{% if purchase_alert.show_stock %}{{ (purchase_alert.display_stock_current if test_notification else purchase_alert.display_stock)|e }}{% endif %}'
PRODUCT_TEXT = '{% if purchase_alert.show_price %}💰 {{ purchase_alert.display_price }}{% if purchase_alert.display_change and not test_notification %} {{ purchase_alert.display_change }}{% endif %}\n{% endif %}{% if purchase_alert.show_stock %}{{ purchase_alert.display_stock_current if test_notification else purchase_alert.display_stock }}\n{% endif %}🎯 {{ purchase_alert.rule_text }}\n🔔 {% if test_notification %}Test notification — no monitoring condition asserted{% else %}{{ purchase_alert.reason_text }}{% endif %}{% if purchase_alert.display_reference_price and not test_notification %}\n📊 Reference: {{ purchase_alert.display_reference_price }}{% endif %}\n{{ watch_open_url or watch_url }}'
PRODUCT_RICH = '{"blocks":[{"type":"heading","text":{% if watch_open_url or watch_url %}{"type":"url","text":{{ (watch_title or "")|tojson }},"url":{{ (watch_open_url or watch_url)|tojson }}}{% else %}{{ (watch_title or "")|tojson }}{% endif %},"size":5}{% if purchase_alert.show_price %},{"type":"paragraph","text":{{ ("💰 " + purchase_alert.display_price + (" " + purchase_alert.display_change if purchase_alert.display_change and not test_notification else ""))|tojson }}}{% endif %}{% if purchase_alert.show_stock %},{"type":"paragraph","text":{{ (purchase_alert.display_stock_current if test_notification else purchase_alert.display_stock or purchase_alert.stock_text)|tojson }}}{% endif %},{"type":"details","summary":"Details","blocks":[{"type":"paragraph","text":{{ ("🎯 " + (purchase_alert.rule_text or "No active rule"))|tojson }}},{"type":"paragraph","text":{{ ("🔔 " + ("Test notification — no monitoring condition asserted" if test_notification else (purchase_alert.reason_text or "Monitoring event")))|tojson }}}{% if purchase_alert.display_reference_price and not test_notification %},{"type":"paragraph","text":{{ ("📊 Reference: " + purchase_alert.display_reference_price)|tojson }}}{% endif %}]}]}'

RICH_INTERNAL_TITLE = '{{ watch_title }}'
# Keep the Apprise title empty. HTML product bodies own their linked title,
# avoiding duplicate titles and any service-specific title escaping.
PRODUCT_HTML_TITLE = '{{ "" }}'

PRESETS = (
    dict(id='builtin-general', name='General webpage change',
         title=default_notification_title, body=default_notification_body,
         format=default_notification_format, builtin=True),
    dict(id='builtin-product-html', name='Telegram product · HTML (foldable)',
         title=PRODUCT_HTML_TITLE, body=PRODUCT_HTML,
         format='telegram_html', builtin=True),
    dict(id='builtin-product-html-expanded', name='Telegram product · HTML (all details)',
         title=PRODUCT_HTML_TITLE, body=PRODUCT_HTML_EXPANDED,
         format='telegram_html', builtin=True),
    dict(id='builtin-product-html-compact', name='Telegram product · HTML (compact)',
         title=PRODUCT_HTML_TITLE, body=PRODUCT_HTML_COMPACT,
         format='telegram_html', builtin=True),
    dict(id='builtin-product-text', name='Product · Plain Text',
         title='{{ watch_title }}', body=PRODUCT_TEXT,
         format='text', builtin=True),
    dict(id='builtin-product-rich', name='Telegram product · Rich details',
         title=RICH_INTERNAL_TITLE, body=PRODUCT_RICH,
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
    rich = item.get('format', 'text') == 'telegram_rich'
    for key, limit in (('name', 100), ('title', 2000), ('body', 20000)):
        value = RICH_INTERNAL_TITLE if rich and key == 'title' else item.get(key)
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
                  'purchase_alert':{'show_price':True,'show_stock':True,
                                    'display_price':'$12.00','display_change':'',
                                    'display_stock':'✅ In stock','display_stock_current':'✅ In stock','stock_text':'In stock',
                                    'rule_text':'Example','reason_text':'Test',
                                    'reference_price':None,'display_reference_price':''}}
        from changedetectionio.jinja2_custom import render
        validate_rich_message(render(template_str=result['body'], **sample))
    return result


def get_templates(datastore):
    stored = datastore.data['settings']['application'].get('notification_templates') or []
    templates = [dict(item) for item in PRESETS] + [dict(item) for item in stored if isinstance(item, dict)]
    for template in templates:
        if template.get('format') == 'telegram_rich':
            template['title'] = RICH_INTERNAL_TITLE
    return templates


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
