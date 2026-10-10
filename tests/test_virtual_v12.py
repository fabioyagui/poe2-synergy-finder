import unittest
from src import pob_engine

class VirtualHelpersTests(unittest.TestCase):
    def test_attribute_colours(self):
        self.assertEqual(pob_engine._support_attribute({"reqStr":20})["attribute"],"STR")
        self.assertEqual(pob_engine._support_attribute({"reqStr":10,"reqDex":10})["attribute"],"HYBRID")
    def test_delta(self):
        rows=pob_engine._delta_rows({"TotalDPS":100,"Cooldown":4},{"TotalDPS":120,"Cooldown":3})
        d={r["key"]:r for r in rows}
        self.assertAlmostEqual(d["TotalDPS"]["pct"],20)
        self.assertAlmostEqual(d["Cooldown"]["pct"],-25)
    def test_fields(self):
        self.assertIn("AreaOfEffectRadiusMetres",pob_engine.COMPARE_FIELDS)
        self.assertIn("Cooldown",pob_engine.COMPARE_FIELDS)
        self.assertIn("Duration",pob_engine.COMPARE_FIELDS)
if __name__=="__main__":unittest.main()
