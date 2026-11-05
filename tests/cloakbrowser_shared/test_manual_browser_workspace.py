"""Visual-only Browsers refactor must retain the existing JS control contract."""
import re
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[2] / 'changedetectionio/blueprint/manual_browser'


class ManualBrowserWorkspaceTests(unittest.TestCase):
    def test_control_ids_are_not_lost(self):
        template = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        required = [
            'manual-csrf', 'manual-watch-uuid', 'manual-existing',
            'manual-existing-title', 'manual-existing-description',
            'manual-resume', 'manual-switch', 'manual-check',
            'manual-back', 'manual-forward', 'manual-url', 'manual-open',
            'manual-go', 'manual-refresh', 'manual-finish', 'manual-close',
            'manual-state', 'manual-connection', 'manual-frame-wrap',
            'manual-frame', 'manual-cover', 'manual-site-data',
            'manual-remaining', 'manual-text',
            'manual-type', 'manual-enter', 'manual-backspace',
        ]
        for element_id in required:
            with self.subTest(element_id=element_id):
                self.assertEqual(template.count('id="' + element_id + '"'), 1)
        self.assertNotIn('onclick=', template)
        self.assertIn('class="manual-viewport-shell"', template)
        self.assertIn('class="manual-cover-label"', template)

    def test_script_order_and_screenshot_flex(self):
        template = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        css = (BASE / 'static/manual-browser.css').read_text(encoding='utf-8')
        self.assertIn("['manual-core.js', 'manual-transport.js', 'manual-stream.js', 'manual-layout.js', 'manual-input.js', 'manual-browser.js']", template)
        self.assertRegex(css, r'\.manual-viewport-shell\s*\{[^}]*flex:1 1 auto')
        self.assertRegex(css, r'\.manual-view\s*\{[^}]*flex:1 1 auto')
        self.assertIn('manual-details', css)


if __name__ == '__main__':
    unittest.main()

# The typing bar is intentionally always visible and the details remain optional.
class ManualBrowserCompactToolbarTests(unittest.TestCase):
    def test_typing_toolbar_precedes_viewport_and_is_not_collapsible(self):
        html = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('id="manual-text"'), 1)
        self.assertLess(html.index('manual-typing-toolbar"'), html.index('class="manual-viewport-shell"'))
        self.assertNotIn('<summary><i data-feather="keyboard"', html)
        self.assertIn('id="manual-session-details"', html)
        for part in ('manual-profile-lock', 'manual-generation', 'manual-cookies',
                     'manual-local-storage', 'manual-frame-latency', 'manual-action-latency', 'manual-fps'):
            self.assertEqual(html.count('id="' + part + '"'), 1)

    def test_old_concatenated_status_removed(self):
        js = (BASE / 'static/manual-stream.js').read_text(encoding='utf-8')
        self.assertNotIn(' | Profile 锁：', js)
        self.assertIn('requestRefresh()', js)
        self.assertIn('frameRequest', js)

class ManualBrowserDiagnosticsContractTests(unittest.TestCase):
    def test_themed_transport_select_and_browser_diagnostics(self):
        html = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        self.assertRegex(html, r'id="manual-transport-mode"[^>]*data-custom-select')
        for element_id in ('manual-ua', 'manual-copy-ua', 'manual-screenshot-ms', 'manual-dispatch-ms',
                           'manual-display-ms', 'manual-frame-bytes', 'manual-ack-ms'):
            with self.subTest(element_id=element_id):
                self.assertEqual(html.count('id="' + element_id + '"'), 1)

    def test_compact_v4_details_contract(self):
        html = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        css = (BASE / 'static/manual-browser.css').read_text(encoding='utf-8')
        for element_id in ('manual-performance-details', 'manual-usage-details',
                           'manual-fps', 'manual-transport-mode'):
            self.assertEqual(html.count('id="' + element_id + '"'), 1)
        for old_id in ('manual-platform', 'manual-viewport', 'manual-dpr'):
            self.assertNotIn('id="' + old_id + '"', html)
        self.assertIn('class="manual-metrics-overview"', html)
        self.assertIn('scrollbar-width:thin', css)
        self.assertIn('manual-environment-ua', css)

    def test_timed_capture_has_separate_execution_and_dispatch_durations(self):
        source = (Path(__file__).resolve().parents[2] / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/manual_session.py').read_text(encoding='utf-8')
        for field in ('screenshot_ms', 'dispatch_ms', 'frame_with_metrics', 'userAgent', 'devicePixelRatio'):
            self.assertIn(field, source)

class ManualBrowserCdpContractTests(unittest.TestCase):
    def test_cdp_is_additive_and_has_themed_selection(self):
        html = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        self.assertRegex(html, r'id="manual-frame-engine"[^>]*data-custom-select')
        self.assertEqual(html.count('value="cdp"'), 1)
        self.assertIn('id="manual-transport-mode"', html)
        self.assertIn('value="http"', html)
        self.assertIn('CDP Screencast', html)

    def test_cdp_stays_on_browser_manager_loop_and_does_not_expose_debug_port(self):
        base = Path(__file__).resolve().parents[2]
        session = (base / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/manual_session.py').read_text()
        screencast = (base / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/manual_screencast.py').read_text()
        self.assertIn('manager.call_sync(self._start_screencast', session)
        self.assertIn('new_cdp_session(page)', screencast)
        self.assertIn("'Page.startScreencast'", screencast)
        self.assertIn("'Page.screencastFrameAck'", screencast)
        self.assertNotIn('remote-debugging-port', screencast)

class ManualBrowserV6ContractTests(unittest.TestCase):
    def test_no_duplicate_url_or_status_and_toolbar_selects(self):
        html = (BASE / 'templates/manual-browser.html').read_text(encoding='utf-8')
        self.assertNotIn('id="manual-detail"', html)
        self.assertNotIn('id="manual-copy-url"', html)
        self.assertNotIn('实时交互画面', html)
        self.assertEqual(html.count('id="manual-finish"'), 1)
        self.assertIn('id="manual-finish" type="button" class="manual-btn manual-btn-primary" hidden', html)
        nav = html[html.index('manual-navigation"'):html.index('manual-actionbar"')]
        self.assertLess(nav.index('id="manual-open"'), nav.index('id="manual-close"'))
        actionbar = html[html.index('manual-actionbar"'):html.index('manual-typing-toolbar"')]
        self.assertIn('id="manual-frame-engine"', actionbar)
        self.assertIn('id="manual-transport-mode"', actionbar)
        details = html[html.index('id="manual-session-details"'):]
        self.assertNotIn('id="manual-frame-engine"', details)

    def test_finish_is_tied_to_actual_owned_watch_context(self):
        entry = (BASE / 'static/manual-browser.js').read_text(encoding='utf-8')
        core = (BASE / 'static/manual-core.js').read_text(encoding='utf-8')
        server = (BASE / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('core.state().watch_uuid === watchUuid', entry)
        self.assertIn('associatedWatchUuid', core)
        self.assertIn("not context.get('watch_uuid')", server)
        self.assertIn("context.get('session') != data.get('session')", server)
