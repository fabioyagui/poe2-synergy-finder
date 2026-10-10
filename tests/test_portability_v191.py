from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src import assets, pob_engine


def make_pob_checkout(root: Path) -> Path:
    src = root / "PathOfBuilding-PoE2" / "src"
    src.mkdir(parents=True)
    (src / "Launch.lua").write_text("", encoding="utf-8")
    (src / "Modules").mkdir()
    lua = root / "PathOfBuilding-PoE2" / "runtime" / "lua"
    lua.mkdir(parents=True)
    (lua / "xml.lua").write_text("return {}", encoding="utf-8")
    return src


def make_bridge(root: Path) -> Path:
    bridge = root / "pob-api"
    (bridge / "API").mkdir(parents=True)
    for rel in ("bootstrap.lua", "HeadlessWrapper.lua", "API/Server.lua", "API/Handlers.lua", "API/BuildOps.lua"):
        p = bridge / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("-- test", encoding="utf-8")
    return bridge


class PortabilityV191Tests(unittest.TestCase):
    def test_repair_rebases_project_owned_paths_after_move(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = make_pob_checkout(root / "engine")
            bridge = make_bridge(root / "engine")
            with mock.patch.object(pob_engine, "LOCAL_POB_CHECKOUT", src.parent), \
                 mock.patch.object(pob_engine, "USER_POB_CHECKOUT", root / "missing-user-checkout"), \
                 mock.patch.object(pob_engine, "BRIDGE_DIR", bridge):
                cfg = {
                    "luajit_path": "C:/still/valid/or/user-managed/luajit.exe",
                    "pob_src_path": "D:/old/location/engine/PathOfBuilding-PoE2/src",
                    "runtime_dll_path": "D:/old/location/engine/PathOfBuilding-PoE2/runtime",
                    "bridge_path": "D:/old/location/engine/pob-api",
                }
                repaired, changed = pob_engine._repair_moved_project_config(cfg)
                self.assertEqual(Path(repaired["pob_src_path"]), src)
                self.assertEqual(Path(repaired["runtime_dll_path"]), src.parent / "runtime")
                self.assertEqual(Path(repaired["bridge_path"]), bridge)
                self.assertEqual(set(changed), {"pob_src_path", "runtime_dll_path", "bridge_path"})
                self.assertEqual(repaired["luajit_path"], cfg["luajit_path"])

    def test_bounded_search_finds_old_checkout_in_custom_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = make_pob_checkout(root / "my-old-project" / "tools" / "engine")
            found = pob_engine._bounded_checkout_search(root, max_depth=6)
            self.assertIn(src, found)

    def test_skill_gem_index_uses_real_icon_dds(self):
        data = {
            "Metadata/Items/Gem/SupportGemTest": {
                "base_item": {"display_name": "Unleash", "release_state": "released"},
                "gem_type": "support",
                "color": "b",
                "icon_dds_file": "Art/2DArt/SkillIcons/Support/4k/UnleashSupport.dds",
            }
        }
        idx = assets._gem_index(data)
        self.assertEqual(idx["unleash"]["asset_kind"], "gem")
        self.assertTrue(idx["unleash"]["dds"].endswith("UnleashSupport.dds"))
        self.assertIn("image.ggpk.exposed", assets.image_url(idx["unleash"]["dds"]))


if __name__ == "__main__":
    unittest.main()
