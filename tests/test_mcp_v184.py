import unittest
import mcp_server

FORBIDDEN={"enum","default","minimum","maximum","maxItems","maxLength","additionalProperties","oneOf","anyOf","allOf"}

def walk(v):
    if isinstance(v,dict):
        for k,x in v.items():
            yield k
            yield from walk(x)
    elif isinstance(v,list):
        for x in v:
            yield from walk(x)

class Mcp184Tests(unittest.TestCase):
    def test_nine_tools_have_codex_safe_schemas(self):
        tools=mcp_server._tool_list()
        self.assertEqual(len(tools),13)
        for tool in tools:
            schema=tool["inputSchema"]
            self.assertEqual(schema["type"],"object")
            self.assertIn("properties",schema)
            self.assertFalse(FORBIDDEN.intersection(set(walk(schema))),tool["name"])

    def test_required_is_preserved(self):
        tools={t["name"]:t for t in mcp_server._tool_list()}
        self.assertEqual(tools["suggest_tree_paths"]["inputSchema"]["required"],["metric"])
        self.assertEqual(tools["preview_tree_change"]["inputSchema"]["required"],["node_id"])

    def test_array_items_remain_typed(self):
        tools={t["name"]:t for t in mcp_server._tool_list()}
        metrics=tools["get_calcs"]["inputSchema"]["properties"]["metrics"]
        self.assertEqual(metrics,{"type":"array","items":{"type":"string"}})

if __name__=="__main__":
    unittest.main()
