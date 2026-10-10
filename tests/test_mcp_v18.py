import json
import unittest
from unittest import mock
import mcp_server

class McpProtocolTests(unittest.TestCase):
    def test_initialize(self):
        r=mcp_server.dispatch({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}})
        self.assertEqual(r["result"]["protocolVersion"],"2025-06-18")
        self.assertIn("tools",r["result"]["capabilities"])

    def test_tools_list_is_compact(self):
        r=mcp_server.dispatch({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        names=[t["name"] for t in r["result"]["tools"]]
        for name in ["get_current_build","get_calcs","suggest_tree_paths","compare_tree_change","search_synergies"]:
            self.assertIn(name,names)
        self.assertNotIn("get_entire_tree",names)
        self.assertNotIn("dump_repoe",names)

    def test_notification_has_no_reply(self):
        self.assertIsNone(mcp_server.dispatch({"jsonrpc":"2.0","method":"notifications/initialized"}))

    def test_tool_error_stays_mcp_result(self):
        with mock.patch.dict(mcp_server.TOOLS,{"boom":{"description":"","schema":{},"call":lambda a:(_ for _ in ()).throw(ValueError("bad"))}},clear=True):
            r=mcp_server.dispatch({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"boom","arguments":{}}})
            self.assertTrue(r["result"]["isError"])
            self.assertIn("bad",r["result"]["content"][0]["text"])

    def test_unknown_tool(self):
        r=mcp_server.dispatch({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"nope","arguments":{}}})
        self.assertTrue(r["result"]["isError"])

    def test_build_compaction_avoids_raw_xml(self):
        d=mcp_server._compact_build({
            "level":93,"class_name":"Mercenary","ascendancy":"Gemling",
            "main_skill":"Oil Grenade","xml":"huge",
            "tree":{"allocated_nodes":151},
            "skills":[{"label":"Oil Grenade","gems":[{"name":"Oil Grenade"},{"name":"Short Fuse II"}]}],
        })
        self.assertNotIn("xml",d)
        self.assertEqual(d["tree"]["allocated_nodes"],151)
        self.assertEqual(d["skills"][0]["gems"][1],"Short Fuse II")

    def test_metric_subset_only_requested(self):
        rows=mcp_server._metric_subset([
            {"key":"Life","label":"Vida","value":100,"category":"Recursos"},
            {"key":"Armour","label":"Armadura","value":200,"category":"Defesa"},
        ],["Life"])
        self.assertEqual([x["key"] for x in rows],["Life"])

if __name__=="__main__":
    unittest.main()
