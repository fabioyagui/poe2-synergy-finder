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

    def test_measure_actor_is_validated(self):
        with self.assertRaises(ValueError):
            service._measure_from({"a": {"field": "TotalDPS", "actor": "totem"}})
        self.assertTrue(callable(service._measure_from({"a": {"field": "TotalDPS", "actor": "minion"}})))

    def test_stats_add_minion_block_only_when_present(self):
        class FakeLab:
            minion = None
            def stats(self, fields=None, minion=False):
                return {"TotalDPS": 0, "Life": 100, "minion": self.minion}
        lab = FakeLab()
        self.assertEqual(service._stats(lab), {"stats": {"Life": 100}})
        lab.minion = {"TotalDPS": 37.04, "Life": 2300, "Nonsense": 1}
        self.assertEqual(service._stats(lab)["minion"], {"TotalDPS": 37.0, "Life": 2300})

    def test_engine_stats_splits_minion_output(self):
        class FakeEngine:
            def is_running(self): return True
            def request(self, action, params, timeout=40):
                if action == "get_classes":
                    return {"result": {"classes": []}}
                self.params = params
                return {"stats": {"_meta": {}, "TotalDPS": 0, "Minion": {"TotalDPS": 37.0, "Nested": {}}}}
        fake = FakeEngine()
        lab = engine.Lab(fake)
        self.assertEqual(lab.stats(["TotalDPS"], minion=True), {"TotalDPS": 0, "minion": {"TotalDPS": 37.0}})
        self.assertIn("Minion", fake.params["fields"])
        fake.request = lambda *a, **k: {"stats": {"TotalDPS": 5}}
        self.assertEqual(lab.stats(["TotalDPS"], minion=True), {"TotalDPS": 5, "minion": None})

    def test_allocate_adds_path_and_reports_pruned_nodes(self):
        nodes = {1: "START", 2: "Perto", 3: "Alvo", 9: "Ilha"}

        class FakeLab:
            def __init__(self):
                self.alloc, self.sets = {1}, []
            def tree_context(self):
                return {"nodes": [{"id": i, "name": n, "allocated": i in self.alloc} for i, n in nodes.items()]}
            def set_nodes(self, cls, wanted, asc=None):
                self.sets.append(set(wanted))
                self.alloc = {x for x in wanted if x != 9}  # o PoB poda o nó sem ligação
            def plan(self, nid, allow_sockets=False):
                assert allow_sockets
                if nid == 9:
                    raise pob_engine.EngineError("x: sem caminho")
                return {"add_ids": [2, 3]}
            def stats(self, fields=None, minion=False):
                return {"Life": 10, "minion": None}

        lab = FakeLab()
        session = {"lab": lab, "class": "Warrior", "ascendancy": "", "log": [], "t0": 0, "selected_key": (1, None)}
        with mock.patch.object(service, "_session", session), mock.patch.object(service, "_current", lambda: session):
            out = service.handle("allocate", {"add": [3, 9]})
        self.assertEqual(out["added"], ["Perto", "Alvo"])
        self.assertEqual(out["path_points"], {"Alvo": 2, "Ilha": 1})
        self.assertEqual(out["dropped"], [{"id": 9, "name": "Ilha"}])
        self.assertIn("Ilha", out["path_errors"])
        with self.assertRaises(ValueError):
            with mock.patch.object(service, "_session", session), mock.patch.object(service, "_current", lambda: session):
                service.handle("allocate", {"add": [404]})

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


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealMinionTests(unittest.TestCase):
    """Huntress/Spirit Walker nível 80, Grand Spear branca: Wolf Pack mostra o DPS do lobo, e The Catha's Balance o aumenta."""

    @classmethod
    def tearDownClass(cls):
        service.handle("close", {})

    def test_wolf_pack_minion_dps_and_catha_balance(self):
        service.handle("open", {"from": "new", "class": "Huntress", "ascendancy": "Spirit Walker", "level": 80, "weapon": "Grand Spear"})
        added = service.handle("add_skill", {"gems": [["Wolf Pack"]]})
        self.assertGreater(added["minion"]["TotalDPS"], 0)
        self.assertNotIn("TotalDPS", added["stats"])  # o jogador não ataca com Wolf Pack
        full = service.handle("allocate", {"add": [765]})  # The Catha's Balance, com o caminho da ascendência
        self.assertIn("The Catha's Balance", full["added"])
        self.assertNotIn("dropped", full)
        path_only = service.handle("allocate", {"remove": [765]})
        self.assertGreater(full["minion"]["TotalDPS"], path_only["minion"]["TotalDPS"] * 1.2)
        self.assertGreater(service.handle("stats", {"fields": ["TotalDPS"]})["minion"]["TotalDPS"], 0)


if __name__ == "__main__":
    unittest.main()
