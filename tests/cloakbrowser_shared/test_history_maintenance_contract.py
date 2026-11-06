"""Worker reservation safety tests without launching Flask or Chromium."""
import importlib.util
import pathlib
import sys
import threading
import time
import types
import unittest

PATH = pathlib.Path(__file__).resolve().parents[2] / 'changedetectionio/worker_pool.py'
logger = types.SimpleNamespace(debug=lambda *a,**k:None, warning=lambda *a,**k:None,
                               error=lambda *a,**k:None, info=lambda *a,**k:None)
old = sys.modules.get('loguru')
sys.modules['loguru'] = types.SimpleNamespace(logger=logger)
spec = importlib.util.spec_from_file_location('worker_pool_maintenance_contract', PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if old is None:
    sys.modules.pop('loguru', None)
else:
    sys.modules['loguru'] = old


class MaintenanceTests(unittest.TestCase):
    def test_claims_blocked_while_maintenance_reservation_exists(self):
        with mod.reserve_watch_maintenance('unit-watch'):
            self.assertFalse(mod.claim_uuid_for_processing('unit-watch', 9))
            self.assertTrue(mod.claim_uuid_for_processing('other-watch', 9))
            mod.release_uuid_from_processing('other-watch', 9)
        self.assertTrue(mod.claim_uuid_for_processing('unit-watch', 9))
        mod.release_uuid_from_processing('unit-watch', 9)

    def test_maintenance_waits_for_existing_worker(self):
        self.assertTrue(mod.claim_uuid_for_processing('running-watch', 1))
        finished = threading.Event()
        def maintenance():
            with mod.reserve_watch_maintenance('running-watch', timeout=2):
                finished.set()
        th = threading.Thread(target=maintenance)
        th.start()
        time.sleep(0.05)
        self.assertFalse(finished.is_set())
        mod.release_uuid_from_processing('running-watch', 1)
        th.join(2)
        self.assertTrue(finished.is_set())

    def test_timeout_releases_reservation(self):
        self.assertTrue(mod.claim_uuid_for_processing('stuck-watch', 1))
        with self.assertRaises(TimeoutError):
            with mod.reserve_watch_maintenance('stuck-watch', timeout=0.01):
                pass
        mod.release_uuid_from_processing('stuck-watch', 1)
        self.assertTrue(mod.claim_uuid_for_processing('stuck-watch', 2))
        mod.release_uuid_from_processing('stuck-watch', 2)


if __name__ == '__main__':
    unittest.main()
