"""Diff do catálogo RePoE do PoE 2: contra si mesmo dá zero; mudanças plantadas numa cópia dos dados reais
são encontradas, e só elas. Sem o snapshot real na máquina, a parte plantada usa um catálogo sintético pequeno.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from src import catalog_diff, storage

SNAPSHOTS = storage.DATA / "raw" / "snapshots"
REAL = catalog_diff.latest_snapshot(SNAPSHOTS) if SNAPSHOTS.is_dir() else None

SYNTHETIC = {
    "skill_gems.min.json": {
        "Metadata/Items/Gems/SkillGemFallingThunder": {"base_item": {"display_name": "Falling Thunder"}, "gem_type": "active", "color": "w",
                                                       "crafting_level": 1, "tags": ["attack", "lightning"], "grants_skills": ["FallingThunderPlayer"]},
        "Metadata/Items/Gems/SkillGemTempestBell": {"base_item": {"display_name": "Tempest Bell"}, "gem_type": "active", "color": "w",
                                                    "crafting_level": 3, "tags": ["attack"], "grants_skills": ["TempestBellPlayer"]},
    },
    "skills.min.json": {
        "FallingThunderPlayer": {"cast_time": 1000, "active_skill": {"types": ["Attack"]}, "static": {}, "per_level": {"1": {"costs": {"Mana": 11}}, "20": {"costs": {"Mana": 76}}},
                                 "stat_sets": [{"id": "FallingThunderPlayer", "static": {"stats": [{"id": "is_area_damage", "value": 1}]},
                                                "per_level": {"1": {"damage_multiplier": 140}, "20": {"damage_multiplier": 437}}}]},
        "TempestBellPlayer": {"cast_time": 1000, "active_skill": {"types": ["Attack"]}, "static": {"cooldown": 500, "stored_uses": 1},
                              "per_level": {"1": {"costs": {"Mana": 12}}}, "stat_sets": []},
        "MonsterSpark": {"cast_time": 800, "active_skill": {"types": ["Spell"]}, "static": {}, "per_level": {"1": {}}, "stat_sets": []},
    },
    "passive_skill_trees/Default.min.json": {"passives": {
        "4": {"hash": 4, "name": "Shock Chance", "is_keystone": False, "is_notable": False, "stats": {"shock_chance_+%": 15}},
        "52": {"hash": 52, "name": "Zealot's Oath", "is_keystone": True, "is_notable": False, "stats": {"keystone_zealots_oath": 1}},
        "16": {"hash": 16, "name": "Life Flask Charges", "ascendancy": "Ranger3", "stats": {"flask_charges_+%": 20}},
    }},
}


def write_catalog(folder: Path, data: dict, version: str):
    for name, payload in data.items():
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"repoe_version": version}), encoding="utf-8")


def load_catalog(folder: Path) -> dict:
    return {name: json.loads((folder / name).read_text(encoding="utf-8-sig")) for name in SYNTHETIC}


def plant(data: dict) -> dict:
    """Muda a cópia: gem nova, gem removida, gem alterada (custo, cooldown, dano por nível), skill sem gem alterada,
    nó novo, nó removido, nó alterado. Devolve o esperado."""
    gems, skills, tree = data["skill_gems.min.json"], data["skills.min.json"], data["passive_skill_trees/Default.min.json"]["passives"]
    ft = next(k for k in gems if k.endswith("SkillGemFallingThunder"))
    bell = next(k for k in gems if k.endswith("SkillGemTempestBell"))
    gems["Metadata/Items/Gems/SkillGemTeste"] = {"base_item": {"display_name": "Gem Teste"}, "gem_type": "active", "color": "w",
                                                 "crafting_level": 5, "tags": ["spell"], "grants_skills": ["TestePlayer"]}
    skills["TestePlayer"] = {"cast_time": 700, "active_skill": {"types": ["Spell"]}, "static": {}, "per_level": {"1": {}}, "stat_sets": []}
    del gems[bell]
    skills["FallingThunderPlayer"]["per_level"]["1"]["costs"]["Mana"] = 99
    skills["FallingThunderPlayer"]["static"]["cooldown"] = 2000
    top = catalog_diff._top_level(skills["FallingThunderPlayer"]["stat_sets"][0]["per_level"])
    skills["FallingThunderPlayer"]["stat_sets"][0]["per_level"][top]["damage_multiplier"] = 500
    other = next(k for k in skills if k not in {"FallingThunderPlayer", "TempestBellPlayer", "TestePlayer"}
                 and not any(k in (g.get("grants_skills") or []) for g in gems.values()))
    skills[other]["cast_time"] = (skills[other].get("cast_time") or 0) + 1
    tree["999999"] = {"hash": 999999, "name": "Nó Teste", "is_keystone": True, "is_notable": False, "stats": {"keystone_teste": 1}}
    removed = next(k for k, n in tree.items() if n.get("name") == "Shock Chance")
    del tree[removed]
    altered = next(k for k, n in tree.items() if n.get("name") == "Zealot's Oath")
    tree[altered]["stats"] = {"keystone_zealots_oath": 2}
    return {"gem_nova": "Metadata/Items/Gems/SkillGemTeste", "gem_removida": bell, "gem_alterada": ft, "skill_sem_gem": other,
            "no_novo": "999999", "no_removido": removed, "no_alterado": altered, "top": top}


class CatalogDiffTests(unittest.TestCase):
    def check(self, source: dict, version: str):
        with tempfile.TemporaryDirectory() as td:
            old, new = Path(td) / "antes", Path(td) / "depois"
            write_catalog(old, source, version)
            same = catalog_diff.diff(old, old)
            self.assertEqual(same["total"], 0, same["resumo"])
            self.assertIn("Nenhuma diferença.", catalog_diff.to_markdown(same))
            planted = copy.deepcopy(source)
            expected = plant(planted)
            write_catalog(new, planted, version + "-teste")
            out = catalog_diff.diff(old, new)
            self.assertEqual([g["id"] for g in out["gems"]["novas"]], [expected["gem_nova"]])
            self.assertEqual([g["id"] for g in out["gems"]["removidas"]], [expected["gem_removida"]])
            self.assertEqual([g["id"] for g in out["gems"]["alteradas"]], [expected["gem_alterada"]])
            fields = {c["campo"] for c in out["gems"]["alteradas"][0]["mudancas"]}
            self.assertEqual(fields, {"skills.FallingThunderPlayer.L1.costs.Mana", "skills.FallingThunderPlayer.static.cooldown",
                                      f"skills.FallingThunderPlayer.stat_sets.FallingThunderPlayer.L{expected['top']}.damage_multiplier"})
            self.assertEqual(out["skills_sem_gem"], {"novas": [], "removidas": [], "alteradas": [expected["skill_sem_gem"]]})
            self.assertEqual([n["hash"] for n in out["arvore"]["novos"]], [expected["no_novo"]])
            self.assertEqual([n["hash"] for n in out["arvore"]["removidos"]], [expected["no_removido"]])
            self.assertEqual([n["hash"] for n in out["arvore"]["alterados"]], [expected["no_alterado"]])
            self.assertEqual(out["total"], 7)
            md = catalog_diff.to_markdown(out)
            self.assertIn("Gem Teste", md)
            self.assertIn("Nó Teste", md)
            self.assertIn("keystone", md)
            result = catalog_diff.run(old, new, name="teste", out_dir=Path(td) / "patch")
            self.assertEqual(result["total"], 7)
            self.assertTrue(Path(result["relatorio"]).exists() and Path(result["json"]).exists())

    def test_synthetic_catalog(self):
        self.check(copy.deepcopy(SYNTHETIC), "0.0")

    @unittest.skipIf(REAL is None, "snapshot real do RePoE ausente em data/raw/snapshots")
    def test_real_snapshot_with_planted_changes(self):
        self.check(load_catalog(REAL), catalog_diff._version(REAL))

    def test_run_refuses_missing_folders(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                catalog_diff.run(Path(td) / "nada", Path(td) / "nada", out_dir=Path(td))


if __name__ == "__main__":
    unittest.main()
