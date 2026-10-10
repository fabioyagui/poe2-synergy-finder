import unittest
from unittest import mock
import mcp_server

class MCPInstance187(unittest.TestCase):
    def test_one_finder_is_selected(self):
        def req(url,path,body=None):
            if url.endswith(':8779'): return {'app_version':'0.18.7'}
            raise mcp_server.FinderError('no')
        with mock.patch.object(mcp_server,'_request',side_effect=req):
            self.assertEqual(mcp_server.discover_url(),'http://127.0.0.1:8779')

    def test_multiple_finders_are_rejected(self):
        def req(url,path,body=None):
            if url.endswith(':8777') or url.endswith(':8778'): return {'app_version':'0.18.6'}
            raise mcp_server.FinderError('no')
        with mock.patch.object(mcp_server,'_request',side_effect=req):
            with self.assertRaises(mcp_server.FinderError) as cm: mcp_server.discover_url()
        self.assertIn('várias instâncias',str(cm.exception))

if __name__=='__main__': unittest.main()
