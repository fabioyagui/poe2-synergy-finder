import unittest
import mcp_server

class Mcp183Tests(unittest.TestCase):
    def test_codex_0154_initialize_shape(self):
        r=mcp_server.dispatch({
            "jsonrpc":"2.0","id":0,"method":"initialize",
            "params":{
                "protocolVersion":"2025-06-18",
                "capabilities":{
                    "experimental":{"codex/auth-change":{}},
                    "elicitation":{"form":{},"url":{}},
                },
                "clientInfo":{"name":"codex-mcp-client","title":"Codex","version":"0.154.0"},
            },
        })
        result=r["result"]
        self.assertEqual(result["protocolVersion"],"2025-06-18")
        self.assertEqual(result["capabilities"],{"tools":{"listChanged":False}})
        self.assertEqual(result["serverInfo"]["name"],"poe2-synergy-finder")

    def test_tools_list_exact_2025_shape(self):
        r=mcp_server.dispatch({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
        self.assertEqual(set(r["result"]),{"tools"})
        self.assertEqual(len(r["result"]["tools"]),13)

    def test_no_2026_result_type(self):
        r=mcp_server.dispatch({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
        self.assertNotIn("resultType",r["result"])

if __name__=="__main__":
    unittest.main()
