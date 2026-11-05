"""Dependency-free maintenance admission and source-boundary checks."""
import importlib.util
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('live_browser_gate_under_test', ROOT / 'changedetectionio/live_browser_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def tearDown(self):
        gate.resume()
        self.assertEqual(gate.status()['active_jobs'], 0)

    def test_pause_blocks_new_work_and_preserves_draining(self):
        self.assertTrue(gate.begin_job())
        gate.pause()
        self.assertFalse(gate.begin_job())
        self.assertFalse(gate.drain(0.001))
        gate.end_job()
        self.assertTrue(gate.drain(0.1))
        self.assertFalse(gate.begin_job())
        gate.resume()
        self.assertTrue(gate.begin_job())
        gate.end_job()

    def test_active_work_decrements_from_other_thread(self):
        self.assertTrue(gate.begin_job())
        gate.pause()
        task = threading.Thread(target=lambda: (time.sleep(.025), gate.end_job()))
        task.start()
        self.assertTrue(gate.drain(.5))
        task.join()

    def test_implementation_keeps_profile_single_writer_and_private_vnc(self):
        manager = (ROOT / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/manager.py').read_text()
        live = (ROOT / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/live_browser.py').read_text()
        route = (ROOT / 'changedetectionio/blueprint/manual_browser/__init__.py').read_text()
        compose = (ROOT / 'docker-compose.yml').read_text()
        self.assertIn('await self._discard_context()', manager)
        self.assertIn('self._live_mode = bool(headed)', manager)
        self.assertIn("'-localhost'", live)
        self.assertIn('manager.switch_live_mode(False)', live)
        self.assertIn('live_browser_gate.pause()', live)
        self.assertIn('live_browser_gate.resume()', live)
        self.assertIn("@_requires_operator\n    def live_websocket", route)
        self.assertNotIn('6080:6080', compose)
        self.assertNotIn('5900:5900', compose)


if __name__ == '__main__':
    unittest.main()
