from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src import pob_engine

class V113Tests(unittest.TestCase):
    def test_gui_install_without_runtime_lua_is_not_valid_src(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/"src"; src.mkdir()
            (src/"Launch.lua").write_text("",encoding="utf-8")
            (src/"Modules").mkdir()
            self.assertFalse(pob_engine._valid_pob_src(src))
            lua=root/"runtime"/"lua"; lua.mkdir(parents=True)
            (lua/"xml.lua").write_text("return {}",encoding="utf-8")
            self.assertTrue(pob_engine._valid_pob_src(src))

    def test_runtime_requires_xml(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            self.assertFalse(pob_engine._valid_runtime_lua_dir(p))
            (p/"xml.lua").write_text("return {}",encoding="utf-8")
            self.assertTrue(pob_engine._valid_runtime_lua_dir(p))

    def test_local_checkout_path(self):
        self.assertEqual(
            pob_engine.LOCAL_POB_CHECKOUT.name,
            "PathOfBuilding-PoE2"
        )

if __name__=="__main__":
    unittest.main()
