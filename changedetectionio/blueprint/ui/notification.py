from flask import Blueprint, request, make_response, jsonify
import random
from loguru import logger

from changedetectionio.store import ChangeDetectionStore
from changedetectionio.auth_decorator import login_optionally_required

def construct_blueprint(datastore: ChangeDetectionStore):
    notification_blueprint = Blueprint('ui_notification', __name__, template_folder="../ui/templates")
    
    @notification_blueprint.route('/notification/templates', methods=['GET', 'POST'])
    @login_optionally_required
    def notification_templates_api():
        from changedetectionio.notification.templates import get_templates, mutate_templates
        if request.method == 'GET':
            return jsonify({'templates': get_templates(datastore)})
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'error': 'JSON object required'}), 400
        try:
            result = mutate_templates(datastore, payload.get('action'), payload.get('template') or {})
        except (ValueError, TypeError) as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception:
            return jsonify({'error': 'Invalid template syntax or storage failure.'}), 400
        return jsonify({'template': result, 'templates': get_templates(datastore)})

    @notification_blueprint.route('/notification/template-preview', methods=['POST'])
    @login_optionally_required
    def notification_template_preview():
        """Render submitted (unsaved) text, without invoking Apprise or mutating watches."""
        from changedetectionio.notification_service import NotificationContextData, set_basic_notification_vars
        from changedetectionio.jinja2_custom import render as render_jinja
        from changedetectionio.notification.templates import validate_template
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'error': 'JSON object required'}), 400
        try:
            template = validate_template(dict(payload, name='Preview'))
            watch_uuid = payload.get('watch_uuid')
            watch = datastore.data.get('watching', {}).get(watch_uuid) if isinstance(watch_uuid, str) else None
            context = NotificationContextData({
                'watch_title': 'Example product', 'watch_url': 'https://example.com/product/123',
                'watch_open_url': 'https://example.com/product/123',
                'diff': 'Example price changed: 1249.99 -> 1199.99',
                'current_snapshot': 'In Stock: True - Price: 1199.99',
                'prev_snapshot': 'In Stock: True - Price: 1249.99',
                'restock': {'title': 'Example product', 'price': '1199.99', 'currency': 'USD', 'in_stock': True},
                'test_notification': True,
                'purchase_alert': {
                    'show_price': True, 'show_stock': True,
                    'display_price': '$1,199.99', 'display_change': '(−4%, ↓ $50.00)',
                    'display_stock': '✅ In stock', 'display_stock_current': '✅ In stock',
                    'display_reference_price': '$1,249.99',
                    'stock_text': 'In stock', 'rule_text': 'price below 1300 USD AND currently in stock',
                    'reason_text': 'Price fell and meets target', 'reference_price': '1249.99',
                    'price_change_amount': '-50.00', 'percent_change': '-4.0',
                    'reason': 'price', 'price_mode': 'below', 'stock_mode': 'in_stock',
                    'price_threshold': '1300', 'price_direction': 'down',
                },
            })
            # Only an explicitly selected Watch supplies actual data; Tag/Global previews
            # never pick a random Watch or accidentally disclose another Watch's content.
            if watch is not None:
                # Do not mix sample product fields into real non-product watches.
                context['restock'] = {}
                context['purchase_alert'] = {'display_price':'Unknown', 'display_change':'', 'stock_text':'Unknown', 'rule_text':'No active rule', 'reason_text':'Test only', 'reference_price':None}
                # Load saved watch tokens, and optionally the two latest snapshots.
                # Never read or modify the watch's active processor or event state.
                snapshots = []
                try:
                    for timestamp in sorted(watch.history.keys(), key=int)[-2:]:
                        snapshots.append(watch.get_history_snapshot(timestamp=timestamp) or '')
                except Exception:
                    snapshots = []
                previous, current = (snapshots[-2], snapshots[-1]) if len(snapshots) >= 2 else ('', snapshots[-1] if snapshots else '')
                context.update(set_basic_notification_vars(current, previous, watch, '', None))
                context['test_notification'] = True
                from changedetectionio.notification_service import add_rendered_diff_to_notification_vars
                context.update(add_rendered_diff_to_notification_vars(
                    prev_snapshot=previous, current_snapshot=current,
                    notification_scan_text=template['title'] + template['body'],
                    word_diff=template['format'] != 'text',
                    escape_output=template['format'].startswith('html'),
                ))
                context['watch_title'] = watch.label
                source = 'watch'
            else:
                source = 'example'
            result = {
                'title': render_jinja(template_str=template['title'], **context),
                'body': render_jinja(template_str=template['body'], **context),
                'format': template['format'], 'source': source,
            }
            return jsonify(result)
        except Exception:
            return jsonify({'error': 'Template could not be rendered. Check the syntax and variables.'}), 400

    # AJAX endpoint for sending a test
    @notification_blueprint.route("/notification/send-test/<string:watch_uuid>", methods=['POST'])
    @notification_blueprint.route("/notification/send-test", methods=['POST'])
    @notification_blueprint.route("/notification/send-test/", methods=['POST'])
    @login_optionally_required
    def ajax_callback_send_notification_test(watch_uuid=None):
        from changedetectionio.notification_service import NotificationContextData, set_basic_notification_vars
        # Watch_uuid could be unset in the case it`s used in tag editor, global settings
        import apprise
        from changedetectionio.notification.handler import process_notification
        from changedetectionio.notification.apprise_plugin.assets import apprise_asset
        from changedetectionio.jinja2_custom import render as jinja_render

        from changedetectionio.notification.apprise_plugin.custom_handlers import apprise_http_custom_handler

        apobj = apprise.Apprise(asset=apprise_asset)

        is_global_settings_form = request.args.get('mode', '') == 'global-settings'
        is_group_settings_form = request.args.get('mode', '') == 'group-settings'

        # Use an existing random one on the global/main settings form
        if not watch_uuid and (is_global_settings_form or is_group_settings_form) \
                and datastore.data.get('watching'):
            logger.debug(f"Send test notification - Choosing random Watch {watch_uuid}")
            watch_uuid = random.choice(list(datastore.data['watching'].keys()))

        if not watch_uuid:
            return make_response("Error: You must have atleast one watch configured for 'test notification' to work", 400)

        watch = datastore.data['watching'].get(watch_uuid)
        notification_urls = request.form.get('notification_urls','').strip().splitlines()

        if not (is_global_settings_form or is_group_settings_form) and watch.get('notification_muted'):
            return make_response('This Watch is muted. Unmute and save before testing.',400)

        # Current, unsaved form values are authoritative. A deliberately empty
        # Watch URL field means "inherit Group/Global", NOT "reuse its saved
        # Watch URLs". Group form tests only send to the field being edited.
        if not notification_urls and not is_global_settings_form and not is_group_settings_form:
            group_tags=[]
            submitted_tags=(request.form.get('tags') or '').strip()
            if submitted_tags:
                for name in submitted_tags.split(','):
                    tag=datastore.tag_exists_by_name(name.strip())
                    if tag:group_tags.append(tag)
            else:
                for tag_uuid in watch.get('tags',[]) or []:
                    tag=datastore.data['settings']['application'].get('tags',{}).get(tag_uuid)
                    if tag:group_tags.append(tag)
            for tag in group_tags:
                if not tag.get('notification_muted') and tag.get('notification_urls'):
                    notification_urls=tag['notification_urls']
                    break
            if not notification_urls:
                notification_urls=datastore.data['settings']['application'].get('notification_urls') or []

        if isinstance(notification_urls,str):
            notification_urls=[v.strip() for v in notification_urls.splitlines() if v.strip()]

        if not notification_urls:
            return make_response('No notification destination configured for this Watch, group or global settings.',400)

        for n_url in notification_urls:
            # We are ONLY validating the apprise:// part here, convert all tags to something so as not to break apprise URLs
            generic_notification_context_data = NotificationContextData()
            generic_notification_context_data.set_random_for_validation()
            n_url = jinja_render(template_str=n_url, **generic_notification_context_data).strip()
            if len(n_url.strip()):
                if not apobj.add(n_url):
                    return make_response('Error: A notification destination is invalid.',400)

        try:
            # use the same as when it is triggered, but then override it with the form test values
            n_object = NotificationContextData({
                'watch_url': request.form.get('window_url', "https://changedetection.io"),
                # Falls back to watch_url when the watch has no 'Link to Open' set
                'watch_open_url': watch.open_link_override or request.form.get('window_url', "https://changedetection.io"),
                'notification_urls': notification_urls,
                'test_notification': True
            })

            # Only use if present, if not set in n_object it should use the default system value
            if 'notification_format' in request.form and request.form['notification_format'].strip():
                n_object['notification_format'] = request.form.get('notification_format', '').strip()
            else:
                n_object['notification_format'] = datastore.data['settings']['application'].get('notification_format')

            if 'notification_title' in request.form and request.form['notification_title'].strip():
                n_object['notification_title'] = request.form.get('notification_title', '').strip()
            elif datastore.data['settings']['application'].get('notification_title'):
                n_object['notification_title'] = datastore.data['settings']['application'].get('notification_title')
            else:
                n_object['notification_title'] = "Test title"

            if 'notification_body' in request.form and request.form['notification_body'].strip():
                n_object['notification_body'] = request.form.get('notification_body', '').strip()
            elif datastore.data['settings']['application'].get('notification_body'):
                n_object['notification_body'] = datastore.data['settings']['application'].get('notification_body')
            else:
                n_object['notification_body'] = "Test body"

            n_object['as_async'] = False

            #  Same like in notification service, should be refactored
            dates = list(watch.history.keys())
            trigger_text = ''
            snapshot_contents = ''

            # Could be called as a 'test notification' with only 1 snapshot available
            prev_snapshot = "Example text: example test\nExample text: change detection is cool\nExample text: some more examples\n"
            current_snapshot = "Example text: example test\nExample text: change detection is fantastic\nExample text: even more examples\nExample text: a lot more examples"

            if len(dates) > 1:
                prev_snapshot = watch.get_history_snapshot(timestamp=dates[-2])
                current_snapshot = watch.get_history_snapshot(timestamp=dates[-1])

            n_object.update(set_basic_notification_vars(current_snapshot=current_snapshot,
                                                        prev_snapshot=prev_snapshot,
                                                        watch=watch,
                                                        triggered_text=trigger_text,
                                                        timestamp_changed=dates[-1] if dates else None))


            sent_obj = process_notification(n_object, datastore)

        except Exception as e:
            logger.warning('Test notification encountered {}',type(e).__name__)
            e_str = str(e)
            # Remove this text which is not important and floods the container
            e_str = e_str.replace(
                "DEBUG - <class 'apprise.decorators.base.CustomNotifyPlugin.instantiate_plugin.<locals>.CustomNotifyPluginWrapper'>",
                '')

            logger.warning('Notification test failed: {}',type(e).__name__)
            return make_response('Notification test failed; inspect Notification debug logs.', 400)

        return 'OK - Sent test notifications'

    return notification_blueprint