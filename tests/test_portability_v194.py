from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src import pob_engine


def make_bridge(root: Path) -> Path:
    bridge = root / "pob-api"
    (bridge / "API").mkdir(parents=True)
    for rel in ("bootstrap.lua", "HeadlessWrapper.lua", "API/Server.lua", "API/Handlers.lua", "API/BuildOps.lua"):
        p = bridge / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("-- test", encoding="utf-8")
    return bridge


class PortabilityV194Tests(unittest.TestCase):
    def test_stable_user_engine_dir_prefers_localappdata(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict("os.environ", {"LOCALAPPDATA": td}, clear=False):
            self.assertEqual(
                pob_engine._stable_user_engine_dir(),
                Path(td) / "PoE2 Synergy Finder" / "engine",
            )

    def test_locked_overlay_falls_back_to_unique_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bridge = make_bridge(root / "source")
            overlay = root / "local" / "pob-api-v0126"
            overlay.mkdir(parents=True)
            (overlay / "locked.txt").write_text("x", encoding="utf-8")

            real_rmtree = pob_engine.shutil.rmtree
            calls = {"n": 0}

            def locked_once(path, *args, **kwargs):
                if Path(path) == overlay and calls["n"] == 0:
                    calls["n"] += 1
                    err = PermissionError(13, "Access is denied", str(path))
                    err.winerror = 5
                    raise err
                return real_rmtree(path, *args, **kwargs)

            identity = lambda text: text
            with mock.patch.object(pob_engine, "BRIDGE_OVERLAY_DIR", overlay), \
                 mock.patch.object(pob_engine.shutil, "rmtree", side_effect=locked_once), \
                 mock.patch.object(pob_engine, "_patch_buildops_exact_support_compat", side_effect=identity), \
                 mock.patch.object(pob_engine, "_patch_buildops_calcs_output", side_effect=identity), \
                 mock.patch.object(pob_engine, "_patch_buildops_native_support_whatif", side_effect=identity), \
                 mock.patch.object(pob_engine, "_patch_handlers_calcs_output", side_effect=identity), \
                 mock.patch.object(pob_engine, "_patch_handlers_native_support_whatif", side_effect=identity), \
                 mock.patch("src.tree_simulator.install_extension", return_value=None), \
                 mock.patch("src.workbench.install_extension", return_value=None):
                out = pob_engine._prepare_bridge_overlay(bridge)

            self.assertNotEqual(out, overlay)
            self.assertEqual(out.parent, overlay.parent)
            self.assertTrue((out / "API" / "BuildOps.lua").is_file())
            real_rmtree(out, ignore_errors=True)
            real_rmtree(overlay, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
