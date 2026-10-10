from pathlib import Path
import tempfile
import unittest

from src import pob_engine

class V115Tests(unittest.TestCase):
    def _base_bridge(self, root: Path, wrapper_text: str):
        (root / "API").mkdir(parents=True)
        for rel in [
            "bootstrap.lua",
            "API/Server.lua",
            "API/Handlers.lua",
            "API/BuildOps.lua",
        ]:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("--", encoding="utf-8")
        (root / "HeadlessWrapper.lua").write_text(wrapper_text, encoding="utf-8")

    def test_master_style_wrapper_does_not_require_simplegraphic(self):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td)
            self._base_bridge(b, 'dofile("Launch.lua")')
            self.assertTrue(pob_engine._valid_bridge(b))

    def test_wrapper_that_mentions_simplegraphic_requires_helper(self):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td)
            self._base_bridge(b, 'dofile("_SimpleGraphic.def.lua")\\ndofile("Launch.lua")')
            self.assertFalse(pob_engine._valid_bridge(b))
            (b / "_SimpleGraphic.def.lua").write_text("-- defs", encoding="utf-8")
            self.assertTrue(pob_engine._valid_bridge(b))

    def test_shim_without_simplegraphic_stays_simple(self):
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "bridge"
            s = Path(td) / "src"
            b.mkdir(); s.mkdir()
            (b / "bootstrap.lua").write_text("dofile('HeadlessWrapper.lua')", encoding="utf-8")
            (b / "HeadlessWrapper.lua").write_text('dofile("Launch.lua")', encoding="utf-8")
            out = pob_engine._make_bootstrap_shim(b, s)
            self.assertIn("HeadlessWrapper.local.lua", out.read_text(encoding="utf-8"))
            local = (b / "HeadlessWrapper.local.lua").read_text(encoding="utf-8")
            self.assertEqual(local, 'dofile("Launch.lua")')

if __name__ == "__main__":
    unittest.main()
