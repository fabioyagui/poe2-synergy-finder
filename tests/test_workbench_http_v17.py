import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest import TestCase,mock
import app
from src import storage,tree_simulator as ts,pob_bridge
from tests.test_workbench_v17 import WorkbenchEngine,HASH
from tests.tree_sim_fixtures import XML,SUMMARY

class WorkbenchHttpTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.engine=WorkbenchEngine()
        cls.patches=[mock.patch.object(storage,'DB',Path(cls.temp.name)/'db.sqlite'),mock.patch.object(ts,'ENGINE',cls.engine),
            mock.patch.object(pob_bridge,'load_current_xml',return_value=XML),mock.patch.object(pob_bridge,'load_current',return_value=SUMMARY)]
        for p in cls.patches:p.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.make_handler(app.Application()));cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        for p in reversed(cls.patches):p.stop()
        cls.temp.cleanup()
    def post(self,path,body,valid=True):
        headers={'Content-Type':'application/json'}
        if valid:headers.update({'Origin':self.url,'X-Local-App':'poe2-explorer'})
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req)as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_tree_visual_read(self):
        status,d=self.post('/api/workbench/visual',{});self.assertEqual(status,200);self.assertTrue(d['original_restored']);self.assertTrue(d['nodes'])
    def test_calcs_exposes_real_response_not_fake_zero(self):
        status,d=self.post('/api/workbench/calcs',{});self.assertEqual(status,200);self.assertEqual(d['output']['Mana'],0);self.assertNotIn('IgniteDPS',d['output'])
    def test_suggestion_route(self):
        status,d=self.post('/api/workbench/suggestions',{'build_hash':HASH,'fingerprint':'fixture:1,2,9'});self.assertEqual(status,200);self.assertEqual(d['eligible'],20)
    def test_cross_origin_blocked(self):
        for route in ['visual','calcs','suggestions']:
            with self.subTest(route=route):self.assertEqual(self.post('/api/workbench/'+route,{},False)[0],403)
    def test_bad_selection(self):self.assertEqual(self.post('/api/workbench/calcs',{'group_index':'hi'})[0],400)
    def test_stale_build(self):self.assertEqual(self.post('/api/workbench/calcs',{'build_hash':'f'*64})[0],409)
    def test_assets_served_with_csp(self):
        for path in ['/workbench.js','/workbench.css']:
            with urllib.request.urlopen(self.url+path)as r:self.assertEqual(r.status,200);self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
