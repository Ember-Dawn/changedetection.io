"""Authenticated rule import/editor and read-only extraction dry-run."""
import json
import os
from functools import wraps
from flask import Blueprint, current_app, render_template, request, jsonify, abort
from flask_login import current_user
from loguru import logger
from changedetectionio.product_extraction import RuleError, load, save, list_rules, evaluate
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
    bp=Blueprint('product_extractors',__name__,template_folder='templates')

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

    @bp.route('/api/save',methods=['POST'])
    @_operator
    def save_rule():
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict):raise RuleError('Expected JSON object')
            return jsonify({'rule':save(data)})
        except (RuleError,ValueError,OSError) as exc:
            return jsonify({'error':str(exc)}),400

    @bp.route('/api/test',methods=['POST'])
    @_operator
    def test_rule():
        """Never mutate a Watch, history, checksum, notification or stored rule."""
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict):raise RuleError('Expected JSON request')
            rule=data.get('rule')
            if rule is None:rule=load(data.get('rule_id',''))
            url=str(data.get('url') or '').strip()
            html=data.get('html')
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
                        await stepper.call_action(action_name='Goto site',selector=None,optional_value=None)
                        from changedetection_cloak_shared.page_readiness import challenge_kind
                        html_result=await stepper.page.content()
                        if challenge_kind(html_result,url=stepper.page.url):
                            raise RuleError('Website verification is displayed; finish it in Manual browser')
                        return html_result
                    finally:
                        await _close_session_resources(session,label=' for product rule dry-run')

                html=run_async_in_browser_loop(fetch(),shared=resolved=='html_cloakbrowser_shared')
            if url:
                from changedetectionio.product_extraction.registry import matches
                if not matches(rule,url):raise RuleError('Rule does not match the test URL')
            result=evaluate(rule,html)
            return jsonify({'result':result.to_dict(),'details':result.field_details,'dry_run':True})
        except RuleError as exc:
            return jsonify({'error':str(exc)}),400
        except Exception as exc:
            logger.warning('Product rule dry-run failed: {}',type(exc).__name__)
            return jsonify({'error':f'Dry-run failed: {type(exc).__name__}'}),502

    return bp
