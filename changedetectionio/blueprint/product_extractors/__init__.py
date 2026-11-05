"""Authenticated rule import/editor and read-only extraction dry-run."""
import json
import base64
import os
from functools import wraps
from flask import Blueprint, current_app, render_template, request, jsonify, abort
from flask_login import current_user
from loguru import logger
from changedetectionio.product_extraction import RuleError, load, save, list_rules, evaluate
from changedetectionio.product_extraction.registry import remove, signature, matches
from changedetectionio.validate_url import is_fetch_url_allowed


def _operator(func):
    @wraps(func)
    def wrapper(*args,**kwargs):
        settings=current_app.config['DATASTORE'].data['settings']['application']
        if (not (settings.get('password') or os.getenv('SALTED_PASS'))
                or current_app.config.get('LOGIN_DISABLED') or not current_user.is_authenticated):
            abort(403,description='Enable application password and sign in to manage product extraction rules')
        return func(*args,**kwargs)
    return wrapper


def construct_blueprint(datastore):
    bp=Blueprint('product_extractors',__name__,template_folder='templates',static_folder='static')

    @bp.route('/',methods=['GET'])
    @_operator
    def index():
        from changedetectionio.blueprint.add_watch_ui import browser_config
        return render_template('product-extractors.html', rules=list_rules(),
            browser_choices=[(name,label) for name,label in browser_config.radio_choices(datastore)
                if browser_config.is_visual_capable(name,datastore)],
            default_backend=browser_config.default_visual_browser(datastore))

    @bp.route('/api/list',methods=['GET'])
    @_operator
    def rules():
        return jsonify({'rules':list_rules()})

    @bp.route('/api/<rid>',methods=['GET'])
    @_operator
    def read(rid):
        try:return jsonify(load(rid))
        except RuleError as exc:return jsonify({'error':str(exc)}),404

    def referencing_watches(rid, rule=None):
        """Prevent deleting rules still used by explicit or auto-mode watches."""
        import pathlib
        references=[]
        tags=datastore.data['settings']['application'].get('tags', {})
        for uuid,watch in datastore.data['watching'].items():
            if watch.get('processor') != 'restock_diff':
                continue
            settings={}
            directory=getattr(watch,'data_dir',None)
            if directory:
                path=pathlib.Path(directory)/'restock_diff.json'
                try:
                    settings=(json.loads(path.read_text(encoding='utf-8')).get('restock_diff') or {})
                except FileNotFoundError:
                    pass
                except (OSError,ValueError):
                    # Fail closed: an unreadable Watch config may reference this rule.
                    references.append({'id':uuid,'title':watch.get('title') or uuid})
                    continue
            for tag_id in watch.get('tags',[]):
                tag=tags.get(tag_id,{})
                if tag.get('overrides_watch'):
                    settings=tag.get('processor_config_restock_diff') or settings
                    break
            mode=settings.get('extraction_mode') or 'auto'
            explicit=mode=='rule' and settings.get('extraction_rule_id')==rid
            automatic=(mode=='auto' and rule and matches(rule,watch.get('url') or ''))
            if explicit or automatic:
                references.append({'id':uuid,'title':watch.get('title') or uuid})
        return references

    @bp.route('/api/<rid>/references',methods=['GET'])
    @_operator
    def references(rid):
        try:
            rule=load(rid)
            return jsonify({'references':referencing_watches(rid,rule)})
        except RuleError as exc:return jsonify({'error':str(exc)}),404

    @bp.route('/api/<rid>/delete',methods=['POST'])
    @_operator
    def delete_rule(rid):
        try:
            data=request.get_json(silent=True) or {}
            rule=load(rid)
            references=referencing_watches(rid,rule)
            if references:
                return jsonify({'error':f'Rule is used by {len(references)} Watches; unbind them first',
                                'references':references}),409
            remove(rid,expected_signature=data.get('expected_signature'))
            return jsonify({'deleted':rid})
        except RuleError as exc:return jsonify({'error':str(exc)}),409
        except OSError:return jsonify({'error':'Could not delete rule file'}),500

    @bp.route('/api/save',methods=['POST'])
    @_operator
    def save_rule():
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict):raise RuleError('Expected JSON object')
            payload=data.get('rule',data)
            result,status=save(payload, expected_signature=data.get('expected_signature'),
                overwrite=data.get('overwrite') is True, return_status=True)
            return jsonify({'rule':result,'revision':signature(result),'status':status})
        except RuleError as exc:
            return jsonify({'error':str(exc)}),409 if 'changed' in str(exc).lower() or 'exists' in str(exc).lower() else 400
        except (ValueError,OSError) as exc:
            return jsonify({'error':str(exc)}),400

    @bp.route('/api/test',methods=['POST'])
    @_operator
    def test_rule():
        """Never mutate a Watch, history, checksum, notification or stored rule."""
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict):raise RuleError('Expected JSON request')
            rule=data.get('rule')
            if rule is None:
                rule=load(data.get('rule_id',''))
            else:
                from changedetectionio.product_extraction.registry import validate
                rule=validate(rule)
            url=str(data.get('url') or '').strip()
            html=data.get('html')
            screenshot=None
            if html is None:
                if not url:raise RuleError('A URL is required to fetch the page')
                allowed,reason=is_fetch_url_allowed(url)
                if not allowed:raise RuleError(reason)
                from changedetectionio.blueprint.add_watch_ui import browser_config
                from changedetectionio.blueprint.browser_steps import (run_async_in_browser_loop,
                    _close_session_resources,acquire_browser_for_fetcher)
                from changedetectionio.browser_steps.browser_steps import browsersteps_live_ui
                selected=data.get('fetch_backend') or browser_config.default_visual_browser(datastore)
                if not browser_config.is_visual_capable(selected,datastore):
                    raise RuleError('Selected backend does not support a browser preview')
                resolved=browser_config.resolve_backend(selected,datastore)

                async def fetch():
                    browser,context=await acquire_browser_for_fetcher(resolved,proxy=None,keepalive_ms=30000)
                    stepper=browsersteps_live_ui(playwright_browser=browser,proxy=None,start_url=url)
                    session={'browserstepper':stepper,'browser':browser,'playwright_context':context}
                    try:
                        await stepper.connect(proxy=None)
                        # Keep live Dry Run and scheduled shared Watch in the same
                        # desktop layout, independent of the operator's WebUI size.
                        from changedetectionio.product_extraction.viewport import desktop_viewport
                        await stepper.page.set_viewport_size(desktop_viewport())
                        await stepper.call_action(action_name='Goto site',selector=None,optional_value=None)
                        delay = rule.get('page', {}).get('extra_wait_seconds', 0)
                        if delay:
                            await stepper.page.wait_for_timeout(delay * 1000)
                        from changedetection_cloak_shared.page_readiness import challenge_kind
                        html_result=await stepper.page.content()
                        if challenge_kind(html_result,url=stepper.page.url):
                            raise RuleError('Website verification is displayed; finish it in Manual browser')
                        # This is an optional, in-memory JPEG from the exact Page
                        # used for HTML extraction. A screenshot error must not
                        # turn a successful extraction into a failed test.
                        image_data = None
                        try:
                            frame = await stepper.page.screenshot(type='jpeg', quality=58,
                                full_page=False, timeout=10000)
                            if len(frame) <= 650_000:
                                image_data = 'data:image/jpeg;base64,' + base64.b64encode(frame).decode('ascii')
                        except Exception as screenshot_error:
                            logger.debug('Dry-run screenshot unavailable: {}',type(screenshot_error).__name__)
                        return html_result, image_data
                    finally:
                        await _close_session_resources(session,label=' for product rule dry-run')

                html,screenshot=run_async_in_browser_loop(fetch(),shared=resolved=='html_cloakbrowser_shared')
            if url:
                from changedetectionio.product_extraction.registry import matches
                if not matches(rule,url):raise RuleError('Rule does not match the test URL')
            result=evaluate(rule,html)
            return jsonify({'result':result.to_dict(),'details':result.field_details,'dry_run':True,'screenshot':screenshot})
        except RuleError as exc:
            return jsonify({'error':str(exc)}),400
        except Exception as exc:
            logger.warning('Product rule dry-run failed: {}',type(exc).__name__)
            return jsonify({'error':f'Dry-run failed: {type(exc).__name__}'}),502

    return bp
