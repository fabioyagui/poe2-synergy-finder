"""Camada pob-layer: árvore do export da GGG por cima do PoB instalado, sem alterar o PoB."""
import json
import tempfile
import unittest
from pathlib import Path

from src import pob_layer

try:
    pob_layer.pob_root()
    pob_layer.luajit()
    TOOL_SKIP = ""
except Exception as exc:  # pragma: no cover
    TOOL_SKIP = f"PoB ou LuaJIT não configurados: {exc}"

GAME_VERSIONS = '''treeVersionList = { "0_4", "0_5" }
latestTreeVersion = treeVersionList[#treeVersionList]
treeVersions = { ["0_5"] = { display = "0_5", num = 0.5 } }
'''


def _layer_with(tmp: Path, versions: dict) -> Path:
    layer = tmp / "layer"
    layer.mkdir()
    (layer / pob_layer.MANIFEST).write_text(json.dumps({"versoes": versions}), encoding="utf-8")
    return layer


class LayerFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        (self.src / "GameVersions.lua").write_text(GAME_VERSIONS, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_prelude_empty_without_versions(self):
        layer = _layer_with(self.root, {})
        self.assertEqual(pob_layer.lua_prelude(layer), "")

    def test_prelude_points_to_layer_and_prefixes(self):
        layer = _layer_with(self.root, {"1_0": {}})
        lua = pob_layer.lua_prelude(layer)
        self.assertTrue(lua.startswith(pob_layer.PRELUDE_MARK))
        self.assertIn(str(layer.resolve()).replace("\\", "/"), lua)
        for prefix in pob_layer.LAYER_PREFIXES:
            self.assertIn(f'"{prefix}"', lua)

    def test_game_versions_appends_only_new_versions(self):
        layer = _layer_with(self.root, {})
        pob_layer.write_game_versions(layer, self.src, ["0_5", "1_0"])
        text = (layer / "GameVersions.lua").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(GAME_VERSIONS.rstrip()))
        self.assertIn('table.insert(treeVersionList, "1_0")', text)
        self.assertNotIn('table.insert(treeVersionList, "0_5")', text)
        self.assertIn('treeVersions["1_0"] = { display = "1_0 (GGG)", num = 1.0 }', text)
        # Sem versão nova, a camada não sobrepõe o GameVersions do PoB.
        pob_layer.write_game_versions(layer, self.src, ["0_5"])
        self.assertFalse((layer / "GameVersions.lua").exists())

    def test_resolve_only_overrides_layer_prefixes(self):
        layer = _layer_with(self.root, {"1_0": {}})
        (layer / "TreeData" / "1_0").mkdir(parents=True)
        (layer / "TreeData" / "1_0" / "tree.json").write_text("{}", encoding="utf-8")
        (layer / "Data").mkdir()
        (layer / "Data" / "ModItem.lua").write_text("return {}", encoding="utf-8")
        (layer / "Modules").mkdir()
        (layer / "Modules" / "Calcs.lua").write_text("return {}", encoding="utf-8")
        self.assertEqual(pob_layer.resolve(self.src, "TreeData/1_0/tree.json", layer),
                         layer / "TreeData" / "1_0" / "tree.json")
        self.assertEqual(pob_layer.resolve(self.src, "TreeData/0_5/tree.json", layer),
                         self.src / "TreeData/0_5/tree.json")
        self.assertEqual(pob_layer.resolve(self.src, "Data/ModItem.lua", layer), layer / "Data" / "ModItem.lua")
        self.assertEqual(pob_layer.resolve(self.src, "Data/Gems.lua", layer), self.src / "Data/Gems.lua")
        # Código do PoB nunca vem da camada.
        self.assertEqual(pob_layer.resolve(self.src, "Modules/Calcs.lua", layer), self.src / "Modules/Calcs.lua")

    def test_files_differ_ignores_line_endings(self):
        a, b, c = self.root / "a.lua", self.root / "b.lua", self.root / "c.lua"
        a.write_bytes(b"return {\r\n\tx = 1,\r\n}\r\n")
        b.write_bytes(b"return {\n\tx = 1,\n}\n")
        c.write_bytes(b"return {\n\tx = 2,\n}\n")
        self.assertFalse(pob_layer._files_differ(a, b))
        self.assertTrue(pob_layer._files_differ(a, c))
        self.assertTrue(pob_layer._files_differ(a, self.root / "missing.lua"))

    def test_status_active_with_data_only(self):
        layer = _layer_with(self.root, {})
        data = json.loads((layer / pob_layer.MANIFEST).read_text(encoding="utf-8"))
        data["dados"] = {"arquivos_mudados": ["ModItem.lua"]}
        (layer / pob_layer.MANIFEST).write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(pob_layer.status(layer)["ativa"])
        self.assertIn('"Data/"', pob_layer.lua_prelude(layer))

    def test_bad_version_and_ref_are_refused(self):
        with self.assertRaises(pob_layer.LayerError):
            pob_layer.build_tree("../x", "main", layer=self.root / "layer", root=self.root)
        with self.assertRaises(pob_layer.LayerError):
            pob_layer.fetch_ggg_tree("main; rm", self.root / "w")


TREE_GGG_OLD = '''return { classes = {}, groups = {}, nodes = {
  [1] = { name = "A", stats = { "10% increased Life\\nand more" }, out = { "2" }, ["in"] = {} },
  [2] = { name = "B", stats = { "20% reduced Spirit Reservation Efficiency of Skills" }, out = {}, ["in"] = { "1" } },
  [3] = { name = "C", stats = { "5% increased Armour" }, icon = "a.png", out = {}, ["in"] = {} },
} }'''
TREE_POB_OLD = '''return { classes = {}, groups = {}, nodes = {
  [1] = { name = "A", stats = { "10% increased Life", "and more" }, out = { "2" }, ["in"] = { "9" }, recipe = { "Fear" } },
  [2] = { name = "B", stats = { "-20% increased Spirit Reservation Efficiency" }, out = {}, ["in"] = { "1" } },
  [3] = { name = "C", stats = { "5% increased Armour" }, icon = "a.dds", applyToArmour = true, out = {}, ["in"] = {} },
  [9] = { name = "Extra", stats = { "3% increased Movement Speed" }, out = { "1" }, ["in"] = {} },
} }'''
TREE_GGG_NEW = '''return { classes = {}, groups = {}, nodes = {
  [1] = { name = "A", stats = { "10% increased Life", "and more" }, out = { "2" }, ["in"] = {} },
  [2] = { name = "B", stats = { "25% reduced Spirit Reservation Efficiency of Skills" }, out = {}, ["in"] = { "1" } },
  [3] = { name = "C", stats = { "5% increased Armour" }, icon = "b.png", out = {}, ["in"] = {} },
} }'''


@unittest.skipIf(TOOL_SKIP, TOOL_SKIP)
class TreeDeltaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name, text in (("ggg_old", TREE_GGG_OLD), ("pob_old", TREE_POB_OLD), ("ggg_new", TREE_GGG_NEW)):
            (self.dir / f"{name}.lua").write_text(text, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_delta_reapplies_where_ggg_did_not_change(self):
        d = self.dir
        delta = pob_layer.run_tool("delta", d / "ggg_old.lua", d / "pob_old.lua", d / "delta.lua")
        self.assertEqual(delta["nos_so_pob"], 1)
        out = pob_layer.run_tool("apply", d / "ggg_new.lua", d / "delta.lua", d / "out.lua")
        # Nó 2: a GGG mudou o texto (20% -> 25%), a correção antiga do PoB não vale mais.
        self.assertEqual([(c["no"], c["campo"]) for c in out["conflitos"]], [(2, "stats")])
        self.assertEqual([n["no"] for n in out["nos_inseridos"]], [9])
        cmp_ = pob_layer.run_tool("compare", d / "out.lua", d / "pob_old.lua")
        # Só sobra a diferença do nó 2; ícone é desenho e não conta.
        self.assertEqual(set(cmp_["campos"]), {"stats"})
        self.assertEqual(cmp_["campos"]["stats"]["exemplos"], [2])
        self.assertEqual(cmp_["so_a"], [])
        self.assertEqual(cmp_["so_b"], [])

    def test_truncated_lua_is_reported(self):
        good, bad = self.dir / "good.lua", self.dir / "bad.lua"
        good.write_text("return { a = 1 }", encoding="utf-8")
        bad.write_text("return {\n\t[1] = {", encoding="utf-8")  # script que morreu no meio da gravação
        errors = pob_layer._lua_syntax_errors([good, bad, self.dir / "notes.txt"])
        self.assertEqual(list(errors), [bad])


if __name__ == "__main__":
    unittest.main()
