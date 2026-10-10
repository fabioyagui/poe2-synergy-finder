from pathlib import Path
import tempfile
import unittest
from unittest import mock
from src import tree_simulator

OLD = """local handlers = {}

handlers.ping = function(params)
  return { ok = true }
end

return handlers
"""

CURRENT = """local handlers = {}

handlers.ping = function(params)
  return { ok = true }
end

return {
  handlers = handlers,
  version_meta = version_meta,
}
"""

NO_LOCAL_CURRENT = """handlers = {}

handlers.ping = function(params)
  return { ok = true }
end

return {
  handlers = handlers,
  version_meta = version_meta,
}
"""

class TreeBridgeInstallerTests(unittest.TestCase):
    def fixture(self, source):
        td=tempfile.TemporaryDirectory()
        root=Path(td.name)
        api=root/"API";api.mkdir(parents=True)
        handlers=api/"Handlers.lua";handlers.write_text(source,encoding="utf-8")
        module=root/"module.lua";module.write_text("-- module",encoding="utf-8")
        return td,root,handlers,module

    def run_install(self, source):
        td,root,handlers,module=self.fixture(source)
        with mock.patch.object(tree_simulator,"MODULE",module):
            tree_simulator.install_extension(root)
        return td,root,handlers

    def test_current_bridge_shape(self):
        td,root,handlers=self.run_install(CURRENT)
        try:
            out=handlers.read_text(encoding="utf-8")
            self.assertIn("-- SYNERGY_TREE_PROTOCOL_1",out)
            self.assertIn('require("API.SynergyTree").install(handlers)',out)
            self.assertIn("handlers = handlers",out)
            self.assertTrue((root/"API"/"SynergyTree.lua").exists())
        finally: td.cleanup()

    def test_old_bridge_shape(self):
        td,root,handlers=self.run_install(OLD)
        try:
            out=handlers.read_text(encoding="utf-8")
            self.assertIn("-- SYNERGY_TREE_PROTOCOL_1",out)
            self.assertIn("return handlers",out)
        finally: td.cleanup()

    def test_idempotent(self):
        td,root,handlers,module=self.fixture(CURRENT)
        try:
            with mock.patch.object(tree_simulator,"MODULE",module):
                tree_simulator.install_extension(root)
                tree_simulator.install_extension(root)
            out=handlers.read_text(encoding="utf-8")
            self.assertEqual(out.count("-- SYNERGY_TREE_PROTOCOL_1"),1)
            self.assertEqual(out.count('require("API.SynergyTree").install(handlers)'),1)
        finally: td.cleanup()

    def test_current_return_table_fallback(self):
        td,root,handlers=self.run_install(NO_LOCAL_CURRENT)
        try:
            out=handlers.read_text(encoding="utf-8")
            marker=out.index("-- SYNERGY_TREE_PROTOCOL_1")
            final_return=out.rindex("\nreturn {\n  handlers = handlers")
            self.assertLess(marker,final_return)
        finally: td.cleanup()

if __name__=="__main__":
    unittest.main()
