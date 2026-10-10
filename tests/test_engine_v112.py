from pathlib import Path
import tempfile
import unittest
from src import pob_engine

class EngineV112Tests(unittest.TestCase):
    def test_bridge_requires_simplegraphic(self):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); (b/"API").mkdir()
            for rel in ["bootstrap.lua","HeadlessWrapper.lua","API/Server.lua","API/Handlers.lua","API/BuildOps.lua"]:
                p=b/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(
                    'dofile("_SimpleGraphic.def.lua")' if rel == "HeadlessWrapper.lua" else "--",
                    encoding="utf-8"
                )
            self.assertFalse(pob_engine._valid_bridge(b))
            (b/"_SimpleGraphic.def.lua").write_text("-- defs",encoding="utf-8")
            self.assertTrue(pob_engine._valid_bridge(b))

    def test_shim_repoints_simplegraphic(self):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td)/"bridge"; s=Path(td)/"src"; b.mkdir(); s.mkdir()
            (b/"bootstrap.lua").write_text("dofile('HeadlessWrapper.lua')",encoding="utf-8")
            (b/"HeadlessWrapper.lua").write_text('dofile("_SimpleGraphic.def.lua")\\ndofile("Launch.lua")',encoding="utf-8")
            (b/"_SimpleGraphic.def.lua").write_text("-- defs",encoding="utf-8")
            out=pob_engine._make_bootstrap_shim(b,s)
            self.assertIn("HeadlessWrapper.local.lua",out.read_text(encoding="utf-8"))
            wrapper=(b/"HeadlessWrapper.local.lua").read_text(encoding="utf-8")
            self.assertNotIn('dofile("_SimpleGraphic.def.lua")',wrapper)
            self.assertIn("_SimpleGraphic.def.lua",wrapper)
            self.assertIn('dofile("Launch.lua")',wrapper)

if __name__=="__main__":
    unittest.main()
