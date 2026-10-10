from pathlib import Path
import json
import os
import tempfile
import textwrap
import unittest
from unittest import mock

from src import pob_engine

class EngineSetupTests(unittest.TestCase):
    def test_pob_src_validation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            p = repo / "src"
            p.mkdir(parents=True)
            self.assertFalse(pob_engine._valid_pob_src(p))
            (p/"Launch.lua").write_text("", encoding="utf-8")
            (p/"Modules").mkdir()
            self.assertFalse(pob_engine._valid_pob_src(p))
            lua=repo/"runtime"/"lua"
            lua.mkdir(parents=True, exist_ok=True)
            (lua/"xml.lua").write_text("return {}",encoding="utf-8")
            self.assertTrue(pob_engine._valid_pob_src(p))

    def test_bridge_validation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            self.assertFalse(pob_engine._valid_bridge(p))
            (p/"API").mkdir()
            for rel in [
                "bootstrap.lua",
                "HeadlessWrapper.lua",
                "_SimpleGraphic.def.lua",
                "API/Server.lua",
                "API/Handlers.lua",
                "API/BuildOps.lua",
            ]:
                q=p/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_text("--",encoding="utf-8")
            self.assertTrue(pob_engine._valid_bridge(p))

    def test_shim_repoints_headless_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td)/"bridge"; s=Path(td)/"src"
            b.mkdir();s.mkdir()
            (b/"bootstrap.lua").write_text("dofile('HeadlessWrapper.lua')",encoding="utf-8")
            (b/"HeadlessWrapper.lua").write_text(
                'dofile("_SimpleGraphic.def.lua")\ndofile("Launch.lua")',
                encoding="utf-8",
            )
            (b/"_SimpleGraphic.def.lua").write_text("-- defs",encoding="utf-8")
            out=pob_engine._make_bootstrap_shim(b,s)
            text=out.read_text(encoding="utf-8")
            self.assertNotIn("dofile('HeadlessWrapper.lua')",text)
            self.assertIn("HeadlessWrapper.local.lua",text)

class FakeProcessProtocolTests(unittest.TestCase):
    def test_expected_bridge_action_shape(self):
        # Protocol contract used by upstream Server.lua: one JSON line with action + params.
        msg=json.dumps({"action":"get_stats","params":{"fields":["Life","TotalDPS"]}})
        parsed=json.loads(msg)
        self.assertEqual(parsed["action"],"get_stats")
        self.assertEqual(parsed["params"]["fields"][1],"TotalDPS")

if __name__=="__main__":
    unittest.main()
