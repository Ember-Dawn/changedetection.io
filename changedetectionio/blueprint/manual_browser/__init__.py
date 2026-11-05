"""Authenticated remote human operation of the *existing* CloakBrowser page.

This is intentionally not covered by login_optionally_required: a live browser
can hold third-party credentials and must never be exposed in anonymous mode.
"""
import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, jsonify, make_response,
                   redirect, render_template, request, session, url_for)
from flask_login import current_user
from flask_wtf.csrf import validate_csrf, ValidationError
from loguru import logger

from changedetectionio.validate_url import is_fetch_url_allowed
from changedetectionio.product_extraction.viewport import desktop_viewport

try:
    from changedetection_cloak_shared.manual_session import ManualSessionError, manual_sessions
    _MANUAL_AVAILABLE = True
except ModuleNotFoundError as exc:
    if exc.name != 'changedetection_cloak_shared':
        raise
    # Keep the ordinary changedetection.io deployment functional when the
    # optional CloakBrowser integration is not installed.
    _MANUAL_AVAILABLE = False
    class ManualSessionError(RuntimeError):
        pass
    manual_sessions = None


def _requires_operator(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if not _MANUAL_AVAILABLE:
            abort(404, description='Optional shared CloakBrowser integration is not installed')
        datastore = current_app.config['DATASTORE']
        password_enabled = bool(datastore.data['settings']['application'].get('password')
                                or os.getenv('SALTED_PASS'))
        if (not password_enabled or current_app.config.get('LOGIN_DISABLED')
                or not current_user.is_authenticated):
            abort(403, description='Enable changedetection.io password authentication and log in to use manual browser control')
        # CSRF-protect image and status GETs as well: they expose the rendered
        # contents of another site's authenticated session. Global CSRFProtect
        # handles the mutating POST requests.
        if request.path.startswith('/manual-browser/api/'):
            try:
                validate_csrf(request.headers.get('X-CSRFToken') or '')
            except ValidationError:
                abort(400, description='Missing or invalid manual browser CSRF token')
            origin = request.headers.get('Origin')
            # Proxies can terminate TLS upstream, so compare the public Host
            # rather than Flask's internal (possibly http) URL scheme.
            if origin and urlsplit(origin).netloc.lower() != request.host.lower():
                abort(403, description='Cross-origin manual browser control blocked')
        response = func(*args, **kwargs)
        return response
    return inner


def _controller_id():
    if '_manual_browser_owner' not in session:
        session['_manual_browser_owner'] = secrets.token_urlsafe(24)
    return session['_manual_browser_owner']


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description='Expected JSON object')
    return data


def construct_blueprint(datastore, update_q, queuedWatchMetaData):
    blueprint = Blueprint('manual_browser', __name__, template_folder='templates',
                          static_folder='static')

    @blueprint.errorhandler(ManualSessionError)
    def session_error(exc):
        return jsonify({'error': str(exc)}), 409

    @blueprint.route('/', methods=['GET'])
    @_requires_operator
    def index():
        watch_uuid = request.args.get('watch_uuid', '').strip()
        initial_url = request.args.get('url', '').strip()
        watch_title = ''
        if watch_uuid:
            watch = datastore.data['watching'].get(watch_uuid)
            if not watch:
                abort(404)
            backend = watch.get_fetch_backend
            if backend == 'system':
                backend = datastore.data['settings']['application'].get('fetch_backend')
            if backend != 'html_cloakbrowser_shared':
                abort(400, description='Manual browser requires the shared CloakBrowser fetch backend')
            initial_url = watch.open_link
            watch_title = watch.label
        # GET renders UI only, it never navigates the server-side browser.
        return render_template('manual-browser.html', initial_url=initial_url,
                               watch_uuid=watch_uuid, watch_title=watch_title,
                               fixed_viewport=desktop_viewport())

    @blueprint.route('/api/current', methods=['GET'])
    @_requires_operator
    def current_session():
        response = jsonify(manual_sessions.inspect(_controller_id()))
        response.headers['Cache-Control'] = 'no-store, private'
        return response

    @blueprint.route('/api/resume', methods=['POST'])
    @_requires_operator
    def resume_session():
        data = _json()
        return jsonify(manual_sessions.resume(data.get('session', ''), _controller_id()))

    @blueprint.route('/api/open', methods=['POST'])
    @_requires_operator
    def open_page():
        data = _json()
        watch_uuid = (data.get('watch_uuid') or '').strip()
        url = str(data.get('url') or '').strip()
        if watch_uuid:
            watch = datastore.data['watching'].get(watch_uuid)
            if not watch:
                abort(404)
            backend = watch.get_fetch_backend
            if backend == 'system':
                backend = datastore.data['settings']['application'].get('fetch_backend')
            if backend != 'html_cloakbrowser_shared':
                abort(400, description='Watch must use the shared CloakBrowser backend')
            url = watch.open_link  # Never trust a caller-controlled URL for a watch UUID.
        if not url.lower().startswith(('http://', 'https://')):
            url = 'https://' + url
        allowed, reason = is_fetch_url_allowed(url)
        if not allowed:
            abort(400, description=reason)
        try:
            result = manual_sessions.open(_controller_id(), url, watch_uuid or None)
        except ManualSessionError:
            raise
        except Exception as exc:
            logger.warning('Unable to open manual browser: {}', type(exc).__name__)
            return jsonify({'error': f'Unable to start manual browser ({type(exc).__name__})'}), 503
        return jsonify(result)

    @blueprint.route('/api/frame', methods=['GET'])
    @_requires_operator
    def frame():
        jpeg = manual_sessions.frame(request.args.get('session', ''), _controller_id())
        result = make_response(jpeg)
        result.headers['Content-Type'] = 'image/jpeg'
        result.headers['Cache-Control'] = 'no-store, private'
        result.headers['X-Content-Type-Options'] = 'nosniff'
        return result

    @blueprint.route('/api/status', methods=['GET'])
    @_requires_operator
    def status():
        result = jsonify(manual_sessions.status(request.args.get('session', ''), _controller_id()))
        result.headers['Cache-Control'] = 'no-store, private'
        return result

    @blueprint.route('/api/action', methods=['POST'])
    @_requires_operator
    def action():
        data = _json()
        return jsonify(manual_sessions.action(data.get('session', ''), _controller_id(),
                                             data.get('action', ''), data))

    def finish_session(recheck=False):
        data = _json()
        if recheck:
            # A finish is meaningful only for an owned, watch-associated session.
            # Reject BEFORE closing, so a mistaken call cannot discard a general session.
            context = manual_sessions.inspect(_controller_id())
            if (not context.get('active') or not context.get('owned')
                    or context.get('session') != data.get('session')
                    or not context.get('watch_uuid')):
                raise ManualSessionError('No associated Watch to recheck')
        watch_uuid = manual_sessions.close(data.get('session', ''), _controller_id())
        queued = False
        if recheck and watch_uuid:
            watch = datastore.data['watching'].get(watch_uuid)
            if watch and not watch.get('paused'):
                from changedetectionio import worker_pool
                if not worker_pool.is_watch_running(watch_uuid) and watch_uuid not in update_q.get_queued_uuids():
                    worker_pool.queue_item_async_safe(update_q, queuedWatchMetaData.PrioritizedItem(
                        priority=1, item={'uuid': watch_uuid}))
                    queued = True
        return jsonify({'closed': True, 'recheck_queued': queued})

    @blueprint.route('/api/close', methods=['POST'])
    @_requires_operator
    def close_page():
        return finish_session()

    @blueprint.route('/api/finish', methods=['POST'])
    @_requires_operator
    def finish_page():
        return finish_session(recheck=True)

    return blueprint
