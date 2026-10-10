import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest import mock
import mcp_server

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def sendj(self,d):
        b=json.dumps(d).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=="/api/status":return self.sendj({"app_version":"0.18.6"})
        if self.path=="/api/pob/current":return self.sendj({"level":93,"class_name":"Mercenary","ascendancy":"Gemling","main_skill":"Oil Grenade","tree":{"allocated_nodes":151},"skills":[]})
        self.send_response(404);self.end_headers()
    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"));body=json.loads(self.rfile.read(length)or b"{}")
        if self.path=="/api/workbench/visual":
            return self.sendj({"build_hash":"a"*64,"fingerprint":"f","groups":[{"index":1,"label":"Oil Grenade","effects":[{"index":1,"name":"Oil Grenade"}]}],"nodes":[{"id":10,"name":"Area node","allocated":False,"path_distance":2,"stats":["8% Area"],"editable":True}]})
        if self.path=="/api/workbench/calcs":
            return self.sendj({"skill":{"name":"Oil Grenade"},"selection":body,"metrics":[{"key":"Life","label":"Vida","value":2495,"category":"Recursos","unit":"","breakdown_available":True,"modifiers_available":True}],"accuracy_note":"fixture","build_hash":"a"*64})
        self.send_response(404);self.end_headers()

class HttpProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),H);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()

    def test_discovery_explicit_env(self):
        with mock.patch.dict("os.environ",{mcp_server.ENV_URL:self.url},clear=False):
            self.assertEqual(mcp_server.discover_url(),self.url)

    def test_build_summary(self):
        with mock.patch("mcp_server.discover_url",return_value=self.url):
            d=mcp_server.tool_build_summary({})
            self.assertEqual(d["main_skill"],"Oil Grenade")
            self.assertEqual(d["tree"]["allocated_nodes"],151)

    def test_calcs_compact(self):
        with mock.patch("mcp_server.discover_url",return_value=self.url):
            d=mcp_server.tool_calcs({"skill":"Oil Grenade","metrics":["Life"]})
            self.assertEqual(d["metrics"][0]["key"],"Life")
            self.assertEqual(d["metrics"][0]["value"],2495)

    def test_search_passive_is_local_filter(self):
        with mock.patch("mcp_server.discover_url",return_value=self.url):
            d=mcp_server.tool_search_passives({"query":"Area"})
            self.assertEqual(d["results"][0]["id"],10)

if __name__=="__main__":
    unittest.main()
