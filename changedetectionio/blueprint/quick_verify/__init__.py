"""Lightweight authenticated verification page using the existing manual browser backend."""
import os
from flask import Blueprint, abort, current_app, make_response, render_template
from flask_login import current_user
from changedetectionio.product_extraction.viewport import desktop_viewport


def construct_blueprint(datastore):
    blueprint = Blueprint('quick_verify', __name__, template_folder='templates', static_folder='static')

    @blueprint.route('/<watch_uuid>', methods=['GET'])
    def index(watch_uuid):
        settings = datastore.data['settings']['application']
        if not (settings.get('password') or os.getenv('SALTED_PASS')) or current_app.config.get('LOGIN_DISABLED'):
            abort(403, description='Quick Verify requires WebUI password authentication')
        if not current_user.is_authenticated:
            # Normal global Flask login handler redirects to the original URL.
            from flask import redirect, url_for
            return redirect(url_for('login', redirect='/verify/' + watch_uuid))
        from changedetectionio.blueprint.manual_browser import _MANUAL_AVAILABLE
        if not _MANUAL_AVAILABLE:
            abort(404)
        watch = datastore.data['watching'].get(watch_uuid)
        if not watch:
            abort(404)
        backend = watch.get_fetch_backend
        if backend == 'system':
            backend = settings.get('fetch_backend')
        if backend != 'html_cloakbrowser_shared':
            abort(400, description='Quick Verify requires shared CloakBrowser')
        response = make_response(render_template('quick-verify.html', watch_uuid=watch_uuid,
                                                 watch_title=watch.label or watch.get('title') or watch.get('url'),
                                                 needs_attention=bool(watch.get('manual_attention_reason')),
                                                 fixed_viewport=desktop_viewport()))
        response.headers['Cache-Control'] = 'no-store, private'
        return response

    return blueprint
