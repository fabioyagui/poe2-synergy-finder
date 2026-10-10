import unittest
from types import SimpleNamespace
from src.tree_points import analyze

def entity(i,name,kind="PASSIVE",hash_value=None,links=None,selectable=True,asc=""):
    return {
        "id":f"id-{i}",
        "name":name,
        "kind":kind,
        "raw_dataset":"tree_nodes",
        "node_hash":hash_value if hash_value is not None else i,
        "node_id":str(i),
        "raw_key":str(i),
        "source_id":f"node:{i}",
        "selectable":selectable,
        "is_notable":kind=="NOTABLE",
        "is_keystone":kind=="KEYSTONE",
        "ascendancy":asc,
        "ascendancy_id":"A1" if asc else "",
        "node_meta":{},
        "summary":f"{name} summary",
        "texts":[{"text":f"{name} effect"}],
        "stats":[],
        "tags":[],
        "links":links or [],
    }

class TreePointTests(unittest.TestCase):
    def cat(self):
        rows=[
            entity("10","Small"),
            entity("20","Big Notable","NOTABLE",links=[{"relation":"AMPLIFIES","concept":"IGNITE","label":"Ignite"}]),
            entity("30","Key","KEYSTONE"),
            entity("40","Asc","ASCENDANCY_NODE",asc="Gemling"),
            entity("50","Weapon spec"),
        ]
        return SimpleNamespace(
            ordered=rows,
            entries={e["id"]:e for e in rows},
            tree_meta={"repoe_version":"4.5.5.2"},
        )

    def test_resolves_pob_refs(self):
        build={"source_type":"pob-xml","tree":{"allocated_nodes":4,"base_hashes":["10","20","30","40"]}}
        d=analyze(self.cat(),build)
        self.assertEqual(d["resolved"],4)
        self.assertEqual(d["unresolved"],0)
        self.assertEqual(d["breakdown"]["notable"],1)
        self.assertEqual(d["breakdown"]["keystone"],1)
        self.assertEqual(d["breakdown"]["ascendancy"],1)
        self.assertEqual(d["detected_point_units"],4)

    def test_preserves_unresolved(self):
        build={"tree":{"base_hashes":["10","999"]}}
        d=analyze(self.cat(),build)
        self.assertEqual(d["resolved"],1)
        self.assertEqual(d["unresolved"],1)
        self.assertEqual(d["nodes"][1]["ref"],"999")

    def test_specialisation_stays_separate(self):
        build={"tree":{"base_hashes":["10"],"specialisations":{"1":["50"]}}}
        d=analyze(self.cat(),build)
        self.assertEqual(d["base_references"],1)
        self.assertEqual(d["specialisation_references"],1)
        spec=next(n for n in d["nodes"] if n["pool"]=="specialisation")
        self.assertEqual(spec["specialisation"],"1")

    def test_allocated_mechanics_are_aggregated(self):
        build={"tree":{"base_hashes":["20"]}}
        d=analyze(self.cat(),build)
        self.assertEqual(d["mechanics"][0]["concept"],"IGNITE")
        self.assertEqual(d["mechanics"][0]["count"],1)

    def test_no_remaining_points_guess(self):
        build={"tree":{"base_hashes":["10"]}}
        d=analyze(self.cat(),build)
        self.assertNotIn("remaining_points",d)

if __name__=="__main__":
    unittest.main()
