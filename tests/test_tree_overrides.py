"""Ascendências alternativas (passive_overrides) entram no catálogo como nós da ascendência nova."""
import unittest

from src import tree_importer


def node(hash_, name, asc=None, **extra):
    n = {"hash": hash_, "name": name, "stats": {}, "is_notable": True, "is_keystone": False, "skill_points": 0,
         "stat_text": [f"{name} text"]}
    if asc:
        n["ascendancy"] = asc
    n.update(extra)
    return n


TREE = {"passives": {
    "1": node(1, "Rupture the Soul", "Witch3"),
    "2": node(2, "Necromantic Conduit", "Witch3"),
    "3": node(3, "Shock Chance"),
}}
ASC = {
    "Witch3": {"name": "Lich", "character": ["x", "Witch"]},
    "Witch3b": {"name": "Abyssal Lich", "character": ["x", "Witch"], "overrides_ascendancy": ["Witch3", 3],
                "passive_overrides": [
                    {"from_hash": 1, "to_passive": node(390, "Rupture the Flesh", "Witch3b")},
                    {"from_hash": 2, "to_passive": node(41162, "Umbral Well")},  # sem ascendancy explícita
                    {"from_hash": 3, "to_passive": {"name": "quebrado"}},  # não tem forma de nó: ignorado
                ]},
}


class TreeOverrideTests(unittest.TestCase):
    def test_override_passives_become_nodes_of_the_alternative_ascendancy(self):
        rows, diag, _edges, nodes = tree_importer.parse(TREE, ASC)
        by_name = {e["name"]: e for e, _raw in rows}
        self.assertEqual(diag["override_nodes"], 2)
        for name in ("Rupture the Flesh", "Umbral Well"):
            e = by_name[name]
            self.assertEqual((e["kind"], e["ascendancy"], e["ascendancy_id"]), ("ASCENDANCY_NODE", "Abyssal Lich", "Witch3b"))
            self.assertIn(f"{name} text", e["summary"])
        self.assertEqual(by_name["Rupture the Flesh"]["node_meta"]["overrides_hash"], 1)
        # os nós da ascendência base continuam lá, intactos
        self.assertEqual(by_name["Rupture the Soul"]["ascendancy"], "Lich")
        self.assertIn("390", nodes)

    def test_existing_hash_is_not_overwritten(self):
        asc = {"Witch3": ASC["Witch3"], "Witch3b": dict(ASC["Witch3b"], passive_overrides=[
            {"from_hash": 1, "to_passive": node(2, "Impostor", "Witch3b")}])}
        rows, diag, _e, _n = tree_importer.parse(TREE, asc)
        self.assertEqual(diag["override_nodes"], 0)
        self.assertNotIn("Impostor", {e["name"] for e, _ in rows})


if __name__ == "__main__":
    unittest.main()
