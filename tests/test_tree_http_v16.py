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
from tests.tree_sim_fixtures import FixtureEngine,XML,SUMMARY

class HttpFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.engine=FixtureEngine()
        cls.patches=[mock.patch.object(storage,'DB',Path(cls.temp.name)/'db.sqlite'),
            mock.patch.object(ts,'ENGINE',cls.engine),mock.patch.object(pob_bridge,'load_current_xml',return_value=XML),
            mock.patch.object(pob_bridge,'load_current',return_value=SUMMARY)]
        for p in cls.patches:p.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.make_handler(app.Application()))
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        for p in reversed(cls.patches):p.stop()
        cls.temp.cleanup()
    def post(self,route,body={},headers=True):
        h={'Content-Type':'application/json'}
        if headers:h.update({'Origin':self.url,'X-Local-App':'poe2-explorer'})
        req=urllib.request.Request(self.url+route,data=json.dumps(body).encode(),headers=h)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_context_plan_compare_end_to_end(self):
        code,c=self.post('/api/tree-sim/context');self.assertEqual(code,200)
        body={'node_id':4,'mode':'path','build_hash':c['build_hash']}
        code,p=self.post('/api/tree-sim/preview',body);self.assertEqual(code,200);self.assertEqual(len(p['changes']),2)
        code,r=self.post('/api/tree-sim/compare',{**body,'fingerprint':p['fingerprint'],'group_index':1,'active_index':1})
        self.assertEqual(code,200);self.assertTrue(r['original_restored']);self.assertEqual(r['variant']['Life'],120)
    def test_get_new_assets(self):
        for route in ['/tree-sim.js','/tree-sim.css']:
            with self.subTest(route=route),urllib.request.urlopen(self.url+route) as r:self.assertEqual(r.status,200)
    def test_cross_origin_write_denied(self):
        self.assertEqual(self.post('/api/tree-sim/context',headers=False)[0],403)
    def test_stale_request_409(self):
        code,r=self.post('/api/tree-sim/preview',{'node_id':3,'mode':'path','build_hash':'f'*64})
        self.assertEqual(code,409)
    def test_invalid_payload_400(self):
        self.assertEqual(self.post('/api/tree-sim/preview',{'node_id':'3'})[0],400)
