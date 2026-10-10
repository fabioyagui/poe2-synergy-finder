from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src import pob_engine


def make_gui_install(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Launch.lua").write_text("", encoding="utf-8")
    (root / "Modules").mkdir(exist_ok=True)
    (root / "Modules" / "Main.lua").write_text("", encoding="utf-8")
    (root / "lua").mkdir(exist_ok=True)
    (root / "lua" / "xml.lua").write_text("return {}", encoding="utf-8")
    return root


class PortabilityV192Tests(unittest.TestCase):
    def test_packaged_gui_layout_is_a_valid_pob_program(self):
        with tempfile.TemporaryDirectory() as td:
            program = make_gui_install(Path(td) / "Path of Building Community (PoE2)")
            self.assertTrue(pob_engine._valid_pob_src(program))
            self.assertEqual(pob_engine._runtime_lua_dir_from_src(program), program / "lua")
            self.assertEqual(pob_engine._runtime_root_from_src(program), program)

    def test_appdata_gui_install_is_discovered_as_program_and_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            appdata = Path(td) / "Roaming"
            program = make_gui_install(appdata / "Path of Building Community (PoE2)")
            with mock.patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False), \
                 mock.patch.object(pob_engine, "LOCAL_POB_CHECKOUT", Path(td) / "missing-local"), \
                 mock.patch.object(pob_engine, "USER_POB_CHECKOUT", Path(td) / "missing-user"), \
                 mock.patch.object(pob_engine, "_sibling_engine_roots", return_value=[]):
                found = pob_engine._pob_install_candidates()
            self.assertIn(program, found)

    def test_runtime_candidates_include_flat_gui_program_root(self):
        with tempfile.TemporaryDirectory() as td:
            program = make_gui_install(Path(td) / "gui")
            found = pob_engine._runtime_candidates(program)
            self.assertIn(program, found)

    def test_auto_detect_uses_valid_runtime_path_as_program_hint(self):
        with tempfile.TemporaryDirectory() as td:
            program = make_gui_install(Path(td) / "Path of Building Community (PoE2)")
            cfg = {
                "luajit_path": "C:/fake/luajit.exe",
                "pob_src_path": "C:/_PathOfBuilding-PoE2/src",
                "runtime_dll_path": str(program),
                "bridge_path": "C:/fake/bridge",
            }
            with mock.patch.object(pob_engine, "load_config", return_value=cfg), \
                 mock.patch.object(pob_engine, "setup_status", side_effect=lambda value: value):
                detected = pob_engine.auto_detect(save=False)
            self.assertEqual(Path(detected["pob_src_path"]), program)
            self.assertEqual(Path(detected["runtime_dll_path"]), program)


if __name__ == "__main__":
    unittest.main()
