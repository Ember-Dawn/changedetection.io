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
            'manual-remaining', 'manual-detail', 'manual-text',
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
        self.assertLess(html.index('class="manual-typing-toolbar"'), html.index('class="manual-viewport-shell"'))
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
