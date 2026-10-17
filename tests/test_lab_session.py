"""Sessão de laboratório (src/lab/service.handle): validação sem motor e um fluxo completo no motor real."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import pob_engine
from src.lab import engine, service

try:
    POB_SKIP = "" if pob_engine.setup_status()["ready"] else "Motor PoB não configurado nesta máquina"
except Exception as exc:  # pragma: no cover
    POB_SKIP = f"diagnóstico do motor falhou: {exc}"


class PureTests(unittest.TestCase):
    def test_unknown_action_and_no_session_are_clear_errors(self):
        with self.assertRaises(ValueError):
            service.handle("explode", {})
        with mock.patch.object(service, "_session", None):
            with self.assertRaises(RuntimeError):
                service.handle("stats", {})

    def test_measure_spec_is_validated(self):
        with self.assertRaises(ValueError):
            service._measure_from({})
        with self.assertRaises(ValueError):
            service._measure_from({"a": {"group": 1}})
        self.assertTrue(callable(service._measure_from({"a": {"group": 1, "field": "TotalDPS"}})))

    def test_xml_groups_lists_skill_groups_in_order(self):
        xml = ('<Skills><SkillSet id="1"><Skill mainActiveSkill="1"><Gem skillId="A" nameSpec="Alpha"/><Gem skillId="S" nameSpec="Sup"/></Skill>'
               '<Skill mainActiveSkill="1"><Gem skillId="B" nameSpec="Beta"/></Skill></SkillSet></Skills>')
        self.assertEqual(engine.xml_groups(xml), [{"index": 1, "gems": ["Alpha", "Sup"], "skill_id": "A"},
                                                  {"index": 2, "gems": ["Beta"], "skill_id": "B"}])

    def test_with_stat_set_can_be_applied_again(self):
        xml = '<Skill><Gem skillId="A" nameSpec="Alpha"/></Skill>'
        twice = engine.with_stat_set(engine.with_stat_set(xml, 2), 3, skill_id="A")
        self.assertEqual(twice.count("<StatSetIndex"), 1)
        self.assertIn('index="3"', twice)
        self.assertNotIn('index="2"', twice)

    def test_pob_code_round_trips(self):
        import base64, zlib
        code = service._pob_code("<PathOfBuilding2/>")
        self.assertEqual(zlib.decompress(base64.b64decode(code.replace("-", "+").replace("_", "/"))).decode(), "<PathOfBuilding2/>")


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealSessionTests(unittest.TestCase):
    """Monk nível 14: Falling Thunder com 3 cargas dá 9 projéteis; export grava XML, código e log."""

    @classmethod
    def tearDownClass(cls):
        service.handle("close", {})

    def test_full_flow(self):
        with self.assertRaises(ValueError):
            service.handle("open", {"from": "new", "class": "Paladin", "level": 14})
        opened = service.handle("open", {"from": "new", "class": "Monk", "level": 14, "weapon": "Gothic Quarterstaff", "name": "teste sessao"})
        self.assertEqual((opened["class"], opened["level"], opened["groups"]), ("Monk", 14, []))

        added = service.handle("add_skill", {"gems": [["Falling Thunder", 5]]})
        self.assertEqual(added["group"], 1)
        service.handle("config", {"values": {"usePowerCharges": True, "overridePowerCharges": 0}})
        melee = service.handle("select", {"group": 1})["stats"]
        proj = service.handle("select", {"group": 1, "part": 2})["stats"]
        self.assertEqual(proj.get("ProjectileCount"), 9)
        self.assertGreater(proj["AverageDamage"], melee["AverageDamage"] * 4)

        equipped = service.handle("equip", {"slot": "Ring 1", "text": "Rarity: MAGIC\nAnel\nIron Ring\nItem Level: 15\nImplicits: 0\n+29 to maximum Life"})
        self.assertAlmostEqual(equipped["stats"]["Life"], proj["Life"] + 29, delta=1.5)  # arredondamento do PoB

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(service, "EXPORT_DIR", Path(td)):
                out = service.handle("export", {"name": "sessao teste"})
            self.assertTrue(Path(out["xml"]).exists() and Path(out["codigo_pob"]).exists())
            log = json.loads(Path(out["log"]).read_text(encoding="utf-8"))
            self.assertEqual([x["action"] for x in log["log"]][:3], ["open", "add_skill", "config"])

        found = service.handle("tree_search", {"budget": 1, "metrics": {"dano": {"group": 1, "part": 2, "field": "TotalDPS"}},
                                               "weights": {"dano": 1}})
        self.assertEqual(len(found["ordem"]), 1)
        self.assertGreater(found["final"]["dano"], proj["TotalDPS"])

        status = service.handle("status", {})
        self.assertTrue(status["open"])
        self.assertEqual(status["groups"][0]["gems"], ["Falling Thunder"])


if __name__ == "__main__":
    unittest.main()
