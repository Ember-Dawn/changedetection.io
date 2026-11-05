"""Regression guards for Live Browser WebSocket route and in-app confirmation."""
import unittest
from pathlib import Path
try:
    from werkzeug.routing import Map, Rule
except ImportError:
    Map = Rule = None

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'changedetectionio/blueprint/manual_browser'


class LiveVncRouteTests(unittest.TestCase):
    def test_websocket_route_uses_werkzeug_upgrade_flag(self):
        source = (BASE / '__init__.py').read_text(encoding='utf-8')
        self.assertIn("@blueprint.route('/live/ws', websocket=True)", source)
        self.assertNotIn("@blueprint.route('/live/ws', methods=['GET'])", source)
        if Map is None:
            self.skipTest('Werkzeug not installed in this offline test runner')
        adapter = Map([Rule('/manual-browser/live/ws', websocket=True, endpoint='live')]).bind('example.test')
        result, _ = adapter.match('/manual-browser/live/ws', websocket=True)
        self.assertEqual(result, 'live')

    def test_url_for_websocket_absolute_url_is_handled(self):
        template = (BASE / 'templates/live-desktop.html').read_text(encoding='utf-8')
        self.assertIn('new URL(', template)
        self.assertIn('endpoint.pathname', template)
        self.assertIn('location.host', template)

    def test_custom_confirmation_is_safe_and_accessible(self):
        template = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        script = (BASE / 'static/manual-live.js').read_text(encoding='utf-8')
        self.assertIn('id="manual-live-confirm"', template)
        self.assertIn('aria-labelledby="manual-live-confirm-title"', template)
        self.assertIn('aria-describedby="manual-live-confirm-description"', template)
        self.assertIn('confirmation.showModal()', script)
        self.assertIn("confirmation.addEventListener('close', onClose)", script)
        self.assertNotIn('confirm(', script)


if __name__ == '__main__':
    unittest.main()
