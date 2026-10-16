import unittest, mcp_server
class SingleToolModeTests(unittest.TestCase):
    def tearDown(self): mcp_server.ACTIVE_TOOL=None
    def test_single_tool(self):
        mcp_server.ACTIVE_TOOL='get_calcs'
        self.assertEqual([x['name'] for x in mcp_server._tool_list()],['get_calcs'])
    def test_all_tools(self):
        mcp_server.ACTIVE_TOOL=None
        self.assertEqual(len(mcp_server._tool_list()),14)
if __name__=='__main__': unittest.main()
