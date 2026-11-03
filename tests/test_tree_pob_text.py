"""Texto do tree.json do PoB 2 para os stats que o RePoE deixa sem tradução.

No RePoE do PoE 2 (4.5.5.2) as keystones vêm traduzidas; o que falta são 79 stats em 68 nós
(ex.: life_regeneration_rate_per_minute_%, life_remnants_gain_per_globe). O PoB tem o texto desses nós.
"""
import json
import tempfile
import unittest
from pathlib import Path

from src import tree_importer


def node(hash_, name, stats, **extra):
    n = {"hash": hash_, "name": name, "stats": stats, "is_notable": True, "is_keystone": False, "skill_points": 0}
    n.update(extra)
    return n


TREE = {"passives": {
    "1": node(1, "Life Regeneration", {"life_regeneration_rate_per_minute_%": 12}),
    "2": node(2, "Sanguimancy", {"skills_gain_base_life_cost": 1, "life_remnants_gain_per_globe": 1}, ascendancy="Witch3"),
    "3": node(3, "Shock Chance", {"shock_chance_+%": 15}),
}}
ASC = {"Witch3": {"name": "Lich", "character": ["x", "Witch"]}}
TRANSLATIONS = {"stat_translations/passive_skill_stat_descriptions.min.json": [
    {"ids": ["shock_chance_+%"], "English": [{"condition": [{}], "format": ["#"], "index_handlers": [[]], "string": "{0}% increased chance to Shock"}]},
    {"ids": ["skills_gain_base_life_cost"], "English": [{"condition": [{}], "format": ["ignore"], "index_handlers": [[]], "string": "Skills gain a Base Life Cost equal to Base Mana Cost"}]},
]}
POB_TREE = {"nodes": {
    "1": {"skill": 1, "name": "Life Regeneration", "stats": ["Regenerate 0.2% of maximum Life per second"]},
    "2": {"skill": 2, "name": "Sanguimancy", "stats": ["Skills gain a Base Life Cost equal to Base Mana Cost\nGrants Skill: Life Remnants"]},
    "3": {"skill": 3, "name": "Shock Chance", "stats": ["15% increased chance to Shock"]},
    "9": {"skill": 9, "name": "Mastery", "isMastery": True, "stats": ["x"]},
}}


class PobTreeTextTests(unittest.TestCase):
    def test_node_texts_split_lines_and_skip_masteries(self):
        texts = tree_importer.node_texts_from_tree(POB_TREE)
        self.assertEqual(texts["2"], ["Skills gain a Base Life Cost equal to Base Mana Cost", "Grants Skill: Life Remnants"])
        self.assertNotIn("9", texts)

    def test_untranslated_stats_get_the_pob_text_and_translated_nodes_do_not(self):
        texts = tree_importer.node_texts_from_tree(POB_TREE)
        rows, diag, _edges, _nodes = tree_importer.parse(TREE, ASC, TRANSLATIONS, node_texts=texts)
        by_name = {e["name"]: e for e, _ in rows}
        regen = by_name["Life Regeneration"]
        self.assertEqual([x["text"] for x in regen["texts"]], ["Regenerate 0.2% of maximum Life per second"])
        self.assertEqual(regen["texts"][0]["source"], "pob_tree")
        sang = by_name["Sanguimancy"]
        self.assertEqual([x["text"] for x in sang["texts"]],
                         ["Skills gain a Base Life Cost equal to Base Mana Cost", "Grants Skill: Life Remnants"])
        self.assertEqual(sum(1 for x in sang["texts"] if x.get("source") == "pob_tree"), 1)
        shock = by_name["Shock Chance"]
        self.assertFalse(any(x.get("source") == "pob_tree" for x in shock["texts"]))
        self.assertEqual((diag["pob_text_nodes"], diag["pob_text_lines"], diag["untranslated_stats"]), (2, 2, 2))

    def test_parse_without_pob_text_keeps_the_old_behaviour(self):
        rows, diag, _e, _n = tree_importer.parse(TREE, ASC, TRANSLATIONS)
        by_name = {e["name"]: e for e, _ in rows}
        self.assertEqual(by_name["Life Regeneration"]["texts"], [])
        self.assertNotIn("pob_text_nodes", diag)

    def test_pob_tree_file_follows_the_latest_version_of_game_versions(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            (src / "GameVersions.lua").write_text('treeVersionList = { "0_1", "0_2" }\n', encoding="utf-8")
            self.assertIsNone(tree_importer.pob_tree_file(src))
            (src / "TreeData" / "0_1").mkdir(parents=True)
            (src / "TreeData" / "0_1" / "tree.json").write_text(json.dumps(POB_TREE), encoding="utf-8")
            self.assertEqual(tree_importer.pob_tree_file(src), src / "TreeData" / "0_1" / "tree.json")
            (src / "TreeData" / "0_2").mkdir(parents=True)
            (src / "TreeData" / "0_2" / "tree.json").write_text(json.dumps(POB_TREE), encoding="utf-8")
            self.assertEqual(tree_importer.pob_tree_file(src), src / "TreeData" / "0_2" / "tree.json")
            table, info = tree_importer.load_node_texts(tree_importer.pob_tree_file(src))
            self.assertEqual((info["tree_version"], info["node_texts"], len(table)), ("0_2", 3, 3))
        self.assertEqual(tree_importer.load_node_texts(None), (None, {"source": "pob_tree", "available": False}))


if __name__ == "__main__":
    unittest.main()
