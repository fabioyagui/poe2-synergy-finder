"""Build por etapas (src/lab/stages, PoE 2): parte pura sempre; o fluxo real no motor é pulado sem o PoB."""
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from src import pob_engine
from src.lab import stages

try:
    POB_SKIP = "" if pob_engine.setup_status()["ready"] else "Motor PoB não configurado nesta máquina"
except Exception as exc:  # pragma: no cover
    POB_SKIP = f"diagnóstico do motor falhou: {exc}"

ACTS = stages.ACTS_FALLBACK
USUAL = {i + 1: req for i, req in enumerate([0, 3, 6, 10, 14, 18, 22, 26, 31, 36, 41, 46, 52, 58, 64, 66, 72, 78, 84, 90])}
TABLES = {"Wolf Pack": USUAL, "Feeding Frenzy I": {1: 0}, "Explosive Spear": USUAL}
TIERS = {"Wolf Pack": 8, "Explosive Spear": 1}

QUESTS = '''return {
\t{
\t\t["Act"] = 1,
\t\t["AreaLevel"] = 10,
\t\t["questPoints"] = 2,
\t},
\t{
\t\t["Act"] = 1,
\t\t["AreaLevel"] = 12,
\t\t["questPoints"] = 2,
\t},
\t{
\t\t["Act"] = 1,
\t\t["AreaLevel"] = 11,
\t\t["Reward"] = "Book",
\t},
\t{
\t\t["Act"] = 2,
\t\t["AreaLevel"] = 28,
\t\t["questPoints"] = 2,
\t},
}'''


def _config_value(xml: str, name: str):
    tag = re.search(r'<Input\b[^>]*name="' + re.escape(name) + r'"[^>]*>', xml)
    return re.search(r'(?:number|string|boolean)="([^"]*)"', tag.group(0)).group(1) if tag else None


def _gem_level(xml: str, name: str) -> int:
    tag = re.search(r'<Gem\b[^>]*nameSpec="' + re.escape(name) + r'"[^>]*>', xml).group(0)
    return int(re.search(r'level="(\d+)"', tag).group(1))


class PureTests(unittest.TestCase):
    def test_stage_filenames(self):
        self.assertEqual(stages.stage_filename(15), "L15.xml")
        self.assertEqual(stages.stage_filename(60, "troca de skill"), "L60 respec - troca de skill.xml")
        self.assertEqual(stages.stage_filename(60, "a/b:c"), "L60 respec - a_b_c.xml")
        self.assertEqual(stages.stage_filename(60, ""), "L60 respec - respec.xml")

    def test_acts_are_built_like_the_pob(self):
        # Pontos somados por ato, o nível do ato é o maior AreaLevel das missões de ponto; recompensa sem ponto não conta.
        self.assertEqual(stages.acts_from_quests(QUESTS), ((1, 0), (12, 4), (28, 6)))

    def test_passive_points_follow_the_quest_table(self):
        self.assertEqual(stages.passive_points(1, ACTS), 0)
        self.assertEqual(stages.passive_points(11, ACTS), 10)
        self.assertEqual(stages.passive_points(12, ACTS), 11 + 4)
        self.assertEqual(stages.passive_points(44, ACTS), 43 + 12)
        self.assertEqual(stages.passive_points(90, ACTS), 89 + 24)
        self.assertEqual(stages.act_index(30, ACTS), 3)

    def test_resistance_penalty_by_act_and_maps(self):
        self.assertEqual([stages.resistance_penalty(l, ACTS) for l in (1, 12, 28, 44, 51, 62, 64, 65, 90)],
                         [0, -10, -20, -30, -40, -50, -50, -60, -60])
        cfg = stages.stage_config(45, ACTS)
        self.assertEqual((cfg["enemyLevel"], cfg["resistancePenalty"]), (45, -30))

    def test_skill_waits_for_its_tier(self):
        groups = stages.parse_gems([["Wolf Pack", "Feeding Frenzy I"], ["Explosive Spear"]])
        plan = lambda lvl: stages.gem_plan(groups, lvl, TABLES.get, TIERS.get)
        at20, at26, at70 = plan(20), plan(26), plan(70)
        self.assertEqual([(g["level"], g["liberada"]) for g in at20[0]], [(6, False), (1, True)])  # tier 8 > gema 6
        self.assertEqual((at26[0][0]["level"], at26[0][0]["liberada"]), (8, True))
        self.assertEqual(at70[0][0]["level"], 16)
        self.assertTrue(at20[1][0]["liberada"])  # tier 1
        self.assertIsNone(at20[0][1]["tier"])  # supports não são barrados pelo tier
        # gem fora do PoB: tabela usual, sem tier
        self.assertEqual(stages.gem_plan([[("Nope", None)]], 14, lambda n: None, lambda n: None)[0][0]["level"], 5)

    def test_parse_gems_accepts_one_group_or_many(self):
        self.assertEqual(stages.parse_gems(["Wolf Pack", {"name": "Muster", "quality": 5}]), [[("Wolf Pack", None), ("Muster", 5)]])
        self.assertEqual(stages.parse_gems([["Wolf Pack"], [["Muster", 5]]]), [[("Wolf Pack", None)], [("Muster", 5)]])
        for bad in ([], "Wolf Pack", [[]], [[3]], ["Wolf Pack", ["Muster", 5]]):
            with self.assertRaises(ValueError):
                stages.parse_gems(bad)

    def test_config_by_level_applies_from_its_level_on(self):
        plan = stages.parse_config({"1": {"conditionEnemyMaimed": True}, "26": {"usePowerCharges": True}})
        self.assertEqual(stages.config_at(plan, 15), {"conditionEnemyMaimed": True})
        self.assertEqual(stages.config_at(plan, 26), {"conditionEnemyMaimed": True, "usePowerCharges": True})
        self.assertEqual(stages.parse_config({"buffOnslaught": True}), {1: {"buffOnslaught": True}})
        self.assertEqual(stages.parse_config(None), {})
        with self.assertRaises(ValueError):
            stages.parse_config({"24": 15})

    def test_nodes_for_keeps_allocation_order_and_budget(self):
        self.assertEqual(stages.nodes_for([9, 8], [1, 2, 3, 8], 3), [9, 8, 1])
        self.assertEqual(stages.nodes_for([], [1, 2, 3], 10), [1, 2, 3])
        self.assertEqual(stages.nodes_for([5], [1], 0), [])

    def test_respecs_are_validated_and_sorted(self):
        out = stages.parse_respecs([{"level": 60, "remove": [1], "add": [2], "motivo": "dano"}, {"level": 30}], {1, 2})
        self.assertEqual([r["level"] for r in out], [30, 60])
        self.assertEqual((out[1]["remove"], out[1]["add"], out[1]["motivo"], out[0]["motivo"]), ([1], [2], "dano", "respec"))
        with self.assertRaises(ValueError):
            stages.parse_respecs([{"level": 60, "add": [99]}], {1, 2})
        with self.assertRaises(ValueError):
            stages.parse_respecs([{"remove": [1]}], {1})

    def test_xml_gems_skip_granted_groups_and_items(self):
        xml = ('<PathOfBuilding2><Items activeItemSet="1"><Item id="1">\n\t\t\tRarity: RARE\nPlano\nIron Ring\nItem Level: 15\n'
               '+8 to Strength\n\t\t</Item><Item id="2">Rarity: NORMAL\nHardwood Spear\nHardwood Spear</Item>'
               '<ItemSet id="1"><Slot name="Ring 1" itemId="1"/><Slot name="Ring 2" itemId="0"/><Slot name="Weapon 1" itemId="2"/>'
               '</ItemSet></Items>'
               '<Skills><SkillSet id="1"><Skill source="Tree:62743"><Gem level="1" nameSpec="Wild Protector"/></Skill>'
               '<Skill><Gem quality="20" level="5" nameSpec="Wolf Pack"/><Gem quality="0" level="1" nameSpec="Muster"/></Skill>'
               '<Skill><Gem level="1" nameSpec="Herald of Ice"/></Skill></SkillSet></Skills></PathOfBuilding2>')
        self.assertEqual(stages.xml_gems(xml), [[("Wolf Pack", 20), ("Muster", None)], [("Herald of Ice", None)]])
        items = stages.xml_items(xml)
        self.assertEqual([(i["slot"], i["nome"], i["base"]) for i in items],
                         [("Ring 1", "Plano", "Iron Ring"), ("Weapon 1", "Hardwood Spear", "Hardwood Spear")])

    def test_render_md_has_one_section_per_stage_and_before_after_for_respec(self):
        cfg = stages.stage_config(60, ACTS)
        common = {"gems": [[{"name": "Wolf Pack", "level": 14, "quality": 20, "tier": 8, "liberada": True},
                            {"name": "Muster", "level": 1, "quality": None, "tier": None, "liberada": True}],
                           [{"name": "Glacial Lance", "level": 0, "quality": None, "tier": 7, "liberada": False}]],
                  "gear": [{"slot": "Ring 1", "nome": "Plano", "base": "Iron Ring"}], "avisos": [], "minion": {"TotalDPS": 400.5}}
        plain = {"arquivo": "L60.xml", "level": 60, "respec": None, "config": cfg, "pontos": {"disponiveis": 83, "usados": 80, "cortados": 0,
                 "ascendencia": 0}, "nos_novos": ["Bond of the Owl"], "nos_removidos": [], "stats": {"TotalDPS": 1234.5, "Life": 2000}, "antes": None, **common}
        respec = {**plain, "arquivo": "L60 respec - dano.xml", "respec": "dano", "nos_removidos": ["Bond of the Owl"], "nos_novos": ["Sic 'Em"],
                  "antes": {"TotalDPS": 1234.5, "Life": 2000}, "stats": {"TotalDPS": 2000.0, "Life": 1900},
                  "pontos": {"disponiveis": 83, "usados": 83, "cortados": 3, "ascendencia": 2}}
        md = stages.render_md("Teste", "Huntress", "Spirit Walker", [plain, respec])
        self.assertIn("## L60\n", md)
        self.assertIn("## L60 respec - dano", md)
        self.assertIn("Wolf Pack 14/20q, Muster 1", md)
        self.assertIn("~~Glacial Lance~~ (tier 7, gema bruta acima do nível 60)", md)
        self.assertIn("| TotalDPS | 1 234.5 | 2 000.0 |", md)
        self.assertIn("Nós que saem: Bond of the Owl.", md)
        self.assertIn("3 do plano fora do orçamento; ascendência: 2 nós", md)
        self.assertIn("Minion da skill principal (um minion): TotalDPS 400.5", md)
        self.assertIn("## Aproximações", md)


class LoadoutTests(unittest.TestCase):
    STAGE = ('<PathOfBuilding2><Build level="{lvl}"/><Notes/><Tree activeSpec="1"><Spec classId="3" nodes="{nodes}"><Sockets><Socket nodeId="9" itemId="2"/></Sockets></Spec></Tree>'
             '<Skills activeSkillSet="1"><SkillSet id="1"><Skill><Gem nameSpec="{gem}"/></Skill></SkillSet></Skills>'
             '<Config activeConfigSet="1"><ConfigSet id="1" title="Default"><Input name="enemyLevel" number="{lvl}"/></ConfigSet></Config>'
             '<Items activeItemSet="1"><Item id="1">Rarity: NORMAL\n{item}\n{item}</Item><Item id="2">Rarity: NORMAL\nAnel\nAnel</Item>'
             '<ItemSet id="1"><Slot name="Weapon 1" itemId="1"/><Slot name="Ring 1" itemId="2"/><Slot name="Ring 2" itemId="0"/></ItemSet></Items></PathOfBuilding2>')

    def test_one_loadout_per_stage_with_unique_item_ids(self):
        a = self.STAGE.format(lvl=15, nodes="1,2", gem="Explosive Spear", item="Hardwood Spear")
        b = self.STAGE.format(lvl=45, nodes="1,2,3", gem="Explosive Spear", item="War Spear")
        root = ET.fromstring(stages.merge_loadouts([("L15", a), ("L45", b)], notes="nota"))
        self.assertEqual([s.get("title") for s in root.findall("Tree/Spec")], ["L15", "L45"])
        self.assertEqual(root.find("Tree").get("activeSpec"), "2")
        self.assertEqual([(s.get("id"), s.get("title")) for s in root.findall("Skills/SkillSet")], [("1", "L15"), ("2", "L45")])
        self.assertEqual([c.get("title") for c in root.findall("Config/ConfigSet")], ["L15", "L45"])
        self.assertEqual([i.get("id") for i in root.findall("Items/Item")], ["1", "2", "3", "4"])
        sets = root.findall("Items/ItemSet")
        self.assertEqual([sl.get("itemId") for sl in sets[1].findall("Slot")], ["3", "4", "0"])
        self.assertEqual([sk.get("itemId") for sk in root.findall("Tree/Spec/Sockets/Socket")], ["2", "4"])
        self.assertEqual(root.find("Notes").text, "nota")
        with self.assertRaises(ValueError):
            stages.merge_loadouts([])


class PobDataTests(unittest.TestCase):
    """Tabelas lidas do PoB instalado (pulado sem o PoB)."""

    def setUp(self):
        from src.lab import data
        try:
            self.info = data.gem_info("Wolf Pack")
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"PoB indisponível: {exc}")

    def test_gem_tables_and_tiers(self):
        from src.lab import data
        self.assertEqual((self.info["levels"][1], self.info["levels"][16], self.info["levels"][20]), (0, 66, 90))
        self.assertFalse(self.info["support"])
        self.assertTrue(data.gem_info("Uul-Netol's Embrace")["lineage"])
        self.assertTrue(data.gem_info("Feeding Frenzy I")["support"])
        self.assertIsNone(data.gem_info("Nope"))
        if self.info.get("tier") is not None:  # tier vem do catálogo importado
            self.assertEqual(self.info["tier"], 8)

    def test_quest_table_from_the_installed_pob(self):
        acts = stages.load_acts()
        self.assertEqual(stages.passive_points(90, acts), 113)
        self.assertEqual(stages.quest_points(11, acts), 0)


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealStagesTests(unittest.TestCase):
    """Huntress de lança: L15, L30 e L45 com gems de níveis diferentes e números medidos em cada etapa."""

    @classmethod
    def tearDownClass(cls):
        from src.lab import service
        service.handle("close", {})

    def test_stages_write_one_build_per_level(self):
        from src.lab import service
        service.handle("open", {"from": "new", "class": "Huntress", "level": 45, "weapon": "Hardwood Spear", "name": "teste etapas"})
        service.handle("add_skill", {"gems": [["Explosive Spear"], ["Rapid Attacks I"]]})
        service.handle("add_skill", {"gems": [["Glacial Lance"]]})  # tier 7: só a partir do nível 22
        service.handle("select", {"group": 1})
        found = service.handle("tree_search", {"budget": 2, "metrics": {"dano": {"group": 1, "field": "CombinedDPS"}},
                                               "weights": {"dano": 1}})
        self.assertEqual(service._session["ordem"], [x["id"] for x in found["ordem"]])
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(service, "EXPORT_DIR", Path(td)):
                out = service.handle("stages", {"levels": [15, 30, 45], "name": "etapas"})
            folder = Path(out["pasta"])
            self.assertEqual(sorted(p.name for p in folder.glob("*.xml")), ["L15.xml", "L30.xml", "L45.xml", "etapas.loadouts.xml"])
            self.assertTrue((folder / "juiz.json").exists() and (folder / "etapas.md").exists())
            l15, l30, l45 = ((folder / f"L{l}.xml").read_text(encoding="utf-8") for l in (15, 30, 45))
            self.assertEqual(_gem_level(l15, "Explosive Spear"), 5)
            self.assertEqual(_gem_level(l30, "Explosive Spear"), 8)
            self.assertNotIn("Glacial Lance", l15)
            self.assertIn("Glacial Lance", l30)
            self.assertEqual(_config_value(l45, "resistancePenalty"), "-30")
            self.assertEqual(_config_value(l30, "resistancePenalty"), "-20")
            md = (folder / "etapas.md").read_text(encoding="utf-8")
            self.assertIn("Aviso: grupo 2 (Glacial Lance) fora da etapa L15: tier 7", md)
        e15, e30, e45 = out["etapas"]
        self.assertEqual((e15["pontos"]["disponiveis"], e15["pontos"]["usados"]), (stages.passive_points(15, stages.load_acts()), 2))
        self.assertGreater(e45["stats"]["Life"], e15["stats"]["Life"])
        self.assertIn("aprovada", out["juiz"])
        status = service.handle("status", {})
        self.assertEqual((status["level"], [g["gems"] for g in status["groups"]]), (45, [["Explosive Spear", "Rapid Attacks I"], ["Glacial Lance"]]))


if __name__ == "__main__":
    unittest.main()
