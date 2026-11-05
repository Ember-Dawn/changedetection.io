import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'integrations/cloakbrowser-shared/changedetection_cloak_shared/headed_geometry.py'
try:
    import loguru
except ImportError:
    sys.modules['loguru'] = types.SimpleNamespace(logger=types.SimpleNamespace(info=lambda *a:None, warning=lambda *a:None))
spec=importlib.util.spec_from_file_location('test_headed_geom',path)
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

def response(stdout='',rc=0):
    return types.SimpleNamespace(stdout=stdout,returncode=rc)

class HeadedGeometryTests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual(g._geometry('X=0\nY=0\nWIDTH=1366\nHEIGHT=900'),(0,0,1366,900))
        self.assertIsNone(g._geometry('bad'))
    def test_fit(self):
        calls=[]
        def fake(*args):
            calls.append(args)
            if args[0]=='search':return response('123\n')
            if args[0]=='getwindowgeometry':
                n=sum(c[0]=='getwindowgeometry' for c in calls)
                return response('X=0\nY=0\nWIDTH=1366\nHEIGHT='+('860' if n==1 else '900'))
            return response()
        with patch.object(g,'_run',side_effect=fake):
            before,after,ok=g._fit_once()
        self.assertTrue(ok)
        self.assertEqual(before,(0,0,1366,860))
        self.assertEqual(after,(0,0,1366,900))
        self.assertIn(('windowsize','123',1366,900),calls)
    def test_no_matching_window(self):
        with patch.object(g,'_run',return_value=response(rc=1)):
            self.assertIsNone(g._fit_once())
