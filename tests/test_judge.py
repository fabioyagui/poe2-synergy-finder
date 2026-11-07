"""Juiz das etapas (src/lab/judge, PoE 2): regras puras sempre; o julgamento real no motor é pulado sem o PoB."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import pob_engine
from src.lab import judge

try:
    POB_SKIP = "" if pob_engine.setup_status()["ready"] else "Motor PoB não configurado nesta máquina"
except Exception as exc:  # pragma: no cover
    POB_SKIP = f"diagnóstico do motor falhou: {exc}"

RING = {"name": "Prismatic Ring", "type": "Ring", "level": 30, "tags": frozenset({"ring", "default"}), "socket_limit": None}


def life(level, lo, hi, group="IncreasedLife", kind="Prefix"):
    return {"id": f"life{lo}", "type": kind, "lines": (f"+({lo}-{hi}) to maximum Life",), "level": level, "group": group,
            "tags": frozenset({"life"})}


POOL = [life(1, 10, 19), life(54, 100, 119), life(60, 120, 149),
        {"id": "fire", "type": "Suffix", "lines": ("+(41-45)% to Fire Resistance",), "level": 82, "group": "FireResistance", "tags": frozenset()},
        {"id": "fire1", "type": "Suffix", "lines": ("+(6-10)% to Fire Resistance",), "level": 1, "group": "FireResistance", "tags": frozenset()},
        {"id": "cold", "type": "Suffix", "lines": ("+(6-10)% to Cold Resistance",), "level": 1, "group": "ColdResistance", "tags": frozenset()},
        {"id": "light", "type": "Suffix", "lines": ("+(6-10)% to Lightning Resistance",), "level": 1, "group": "LightningResistance", "tags": frozenset()},
        {"id": "chaos", "type": "Suffix", "lines": ("+(4-7)% to Chaos Resistance",), "level": 1, "group": "ChaosResistance", "tags": frozenset()},
        {"id": "mana", "type": "Prefix", "lines": ("+(10-14) to maximum Mana",), "level": 1, "group": "IncreasedMana", "tags": frozenset()}]

USUAL = {i + 1: req for i, req in enumerate([0, 3, 6, 10, 14, 18, 22, 26, 31, 36, 41, 46, 52, 58, 64, 66, 72, 78, 84, 90])}
GEMS = {
    "Wolf Pack": {"support": False, "levels": USUAL, "tier": 8, "tags": frozenset({"minion", "companion"})},
    "Explosive Spear": {"support": False, "levels": USUAL, "tier": 1, "tags": frozenset({"attack", "fire"})},
    "Despair": {"support": False, "levels": USUAL, "tier": 1, "tags": frozenset({"curse", "spell"})},
    "Enfeeble": {"support": False, "levels": USUAL, "tier": 1, "tags": frozenset({"curse", "spell"})},
    "Sniper's Mark": {"support": False, "levels": USUAL, "tier": 1, "tags": frozenset({"mark"})},
    "Wild Protector": {"support": False, "levels": USUAL, "tier": 0, "tags": frozenset({"minion"})},
    "Uul-Netol's Embrace": {"support": True, "lineage": True, "levels": {1: 0}, "tags": frozenset({"support"})},
    **{s: {"support": True, "levels": {1: 0}, "tags": frozenset({"support"})}
       for s in ("Feeding Frenzy I", "Rapid Attacks II", "Hulking Minions", "Muster", "Heavy Swing", "Minion Mastery")},
}
gem_of = lambda n: GEMS.get(n, {})


def item(explicits, ilvl=60, rarity="RARE", implicits=()):
    return {"rarity": rarity, "name": "Teste", "base": "Prismatic Ring", "item_level": ilvl, "level_req": None,
            "implicits": list(implicits), "explicits": list(explicits), "especiais": []}


def build_xml(level=70, gems=(), items="", slots="", config='<Input name="resistancePenalty" number="-60"/>', nodes="1"):
    skills = "".join(f'<Skill enabled="true"{" source=" + chr(34) + src + chr(34) if src else ""}>' +
                     "".join(f'<Gem nameSpec="{n}" level="{l}" enabled="true"/>' for n, l in group) + "</Skill>"
                     for src, group in gems)
    return (f'<PathOfBuilding2><Build level="{level}" className="Huntress" ascendClassName="Spirit Walker"/>'
            f'<Tree activeSpec="1"><Spec nodes="{nodes}"/></Tree>'
            f'<Skills activeSkillSet="1"><SkillSet id="1">{skills}</SkillSet></Skills>'
            f'<Items activeItemSet="1">{items}<ItemSet id="1">{slots}</ItemSet></Items>'
            f'<Config activeConfigSet="1"><ConfigSet id="1">{config}</ConfigSet></Config></PathOfBuilding2>')


GOOD = {"FireResist": 75, "ColdResist": 75, "LightningResist": 75, "Life": 4000, "CombinedDPS": 100, "TotalEHP": 400,
        "Spirit": 100, "SpiritUnreserved": 40}
TREE = {1: {"kind": "ClassStart", "name": "RANGER"}}


def verdict(xml, stats=None, trilha=None, bases=None, tree=TREE, allocated=(1,), minion=None):
    return judge.judge_stage(xml, {"stats": {**GOOD, **(stats or {})}, "tree": tree, "allocated": list(allocated), "minion": minion},
                             trilha=trilha, gem_of=gem_of, bases=bases or {}, pool_of=lambda b: POOL)


class ItemRules(unittest.TestCase):
    def test_tier_within_item_level_passes(self):
        self.assertEqual(judge.check_item(item(["+119 to maximum Life", "+8% to Fire Resistance"]), RING, POOL), [])

    def test_value_above_tier_for_item_level_fails(self):
        fails = judge.check_item(item(["+149 to maximum Life"], ilvl=55), RING, POOL)
        self.assertEqual([f["regra"] for f in fails], ["gear: tier"])
        self.assertIn("exige item level 60", fails[0]["motivo"])
        self.assertIn("teto no ilvl 55 é 119", fails[0]["motivo"])

    def test_unknown_line_and_too_many_suffixes_fail(self):
        self.assertEqual([f["regra"] for f in judge.check_item(item(["+2 to Level of all Awesome Skills"]), RING, POOL)], ["gear: mod"])
        lines = ["+8% to Fire Resistance", "+8% to Cold Resistance", "+8% to Lightning Resistance", "+5% to Chaos Resistance"]
        self.assertEqual([f["regra"] for f in judge.check_item(item(lines), RING, POOL)], ["gear: afixos"])
        self.assertEqual(judge.check_item(item(lines[:3]), RING, POOL), [])

    def test_magic_item_allows_one_prefix_and_one_suffix(self):
        self.assertEqual(judge.check_item(item(["+119 to maximum Life", "+8% to Fire Resistance"], rarity="MAGIC"), RING, POOL), [])
        fails = judge.check_item(item(["+119 to maximum Life", "+12 to maximum Mana"], rarity="MAGIC"), RING, POOL)
        self.assertEqual([f["regra"] for f in fails], ["gear: afixos"])

    def test_parse_item_keeps_runes_out_of_explicits(self):
        parsed = judge.parse_item("Rarity: RARE\nPeito\nTournament Mail\nItem Level: 82\nQuality: 20\nSockets: S S\n"
                                  "Rune: Desert Rune\nRune: None\nLevelReq: 65\nImplicits: 1\n{rune}+12% to Fire Resistance\n"
                                  "+205 to maximum Life\n{desecrated}+20% to Chaos Resistance\nGrants Skill: Level 20 Cackling Companions")
        self.assertEqual((parsed["base"], parsed["item_level"], parsed["level_req"], parsed["rune_sockets"]), ("Tournament Mail", 82, 65, 2))
        self.assertEqual(parsed["runes"], ["Desert Rune", "None"])
        self.assertEqual(parsed["implicits"], ["+12% to Fire Resistance"])
        self.assertEqual(parsed["explicits"], ["+205 to maximum Life", "Grants Skill: Level 20 Cackling Companions"])
        self.assertEqual(parsed["especiais"], ["+20% to Chaos Resistance"])
        self.assertEqual(parsed["grants"], ["Cackling Companions"])


class TablesAndRecords(unittest.TestCase):
    def test_ascendancy_points_by_ascension(self):
        self.assertEqual([judge.ascendancy_points(l) for l in (15, 21, 22, 37, 38, 59, 60, 75, 90)], [0, 0, 2, 2, 4, 4, 6, 8, 8])

    def test_targets_and_item_level(self):
        self.assertEqual(judge.meta_for(15)["resistencia"], 0)
        self.assertEqual(judge.meta_for(51)["resistencia"], 0)  # campanha não cobra resistência (autor, 2026-11-05)
        self.assertEqual([judge.campaign_gear(l) for l in (1, 15, 16, 33, 46, 64)], [(3, 1), (3, 1), (5, 1), (10, 1), (10, 2), (10, 2)])
        self.assertEqual(judge.meta_for(65), {"desde": 65, "resistencia": 75, "vida_es": 2800})
        self.assertEqual(judge.max_item_level(30), 32)
        self.assertEqual(judge.max_item_level(90), 82)

    def test_mana_rhythm_for_duration_dots(self):
        hit = {"ManaCost": 60, "Speed": 2.0, "Duration": 2.0, "TotalDPS": 1000, "TotalDot": 0, "ManaPerSecondCost": 120}
        self.assertEqual(judge.mana_per_second(hit), 120)
        dot = {**hit, "TotalDPS": 0, "TotalDot": 1000}
        self.assertEqual(judge.mana_per_second(dot), 30)
        self.assertIsNone(judge.mana_per_second({"ManaCost": 0}))  # minion persistente: sem custo por uso

    def test_anchor_record_is_required_with_two_alternatives_and_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(judge.check_anchor(Path(tmp))["ok"])
            path = Path(tmp) / judge.ANCHOR_FILE
            path.write_text("# Skill\nWolf Pack\n# Por que\nx\n# Alternativas\n- Explosive Spear: menos\n# Evidência\nlab\n", encoding="utf-8")
            self.assertIn("1 alternativa", judge.check_anchor(Path(tmp))["motivo"])
            path.write_text(path.read_text(encoding="utf-8").replace("menos", "menos\n- Glacial Lance: x"), encoding="utf-8")
            self.assertIn("Trilha", judge.check_anchor(Path(tmp))["motivo"])
            path.write_text(path.read_text(encoding="utf-8").replace("Wolf Pack\n", "Wolf Pack\nTrilha: desbalanceada\n"), encoding="utf-8")
            self.assertEqual(judge.check_anchor(Path(tmp))["trilha"], "desbalanceada")
        self.assertIsNone(judge.check_anchor(None)["ok"])

    def test_declared_points(self):
        md = "## L15\n\nPontos: 16 de 18 disponíveis.\n\n## L30 respec - troca\n\nPontos: 35 de 37 disponíveis.\n"
        self.assertEqual(judge.declared_stages(md), {"L15": {"pontos": 16}, "L30 respec - troca": {"pontos": 35}})


class StageRules(unittest.TestCase):
    def test_supports_per_track_and_lineage(self):
        five = [("Wolf Pack", 16), ("Feeding Frenzy I", 1), ("Uul-Netol's Embrace", 1), ("Rapid Attacks II", 1), ("Hulking Minions", 1), ("Muster", 1)]
        xml = build_xml(level=70, gems=[(None, five)])
        starter = verdict(xml, trilha="starter")
        rules = [f["motivo"] for f in starter["reprovas"]]
        self.assertTrue(any("5 supports no L70; na trilha starter o degrau fecha em 4" in m for m in rules))
        self.assertTrue(any("Uul-Netol's Embrace é support lineage" in m for m in rules))
        self.assertTrue(verdict(xml, trilha="desbalanceada")["aprovada"])
        six = build_xml(level=70, gems=[(None, five + [("Heavy Swing", 1)])])
        self.assertTrue(any("o jogo permite 5" in f["motivo"] for f in verdict(six, trilha="desbalanceada")["reprovas"]))
        twice = build_xml(level=70, gems=[(None, [("Wolf Pack", 16), ("Uul-Netol's Embrace", 1)]),
                                          (None, [("Explosive Spear", 16), ("Uul-Netol's Embrace", 1)])])
        self.assertTrue(any("lineage é um só por personagem" in f["motivo"] for f in verdict(twice, trilha="desbalanceada")["reprovas"]))

    def test_skill_tier_and_gem_level(self):
        early = verdict(build_xml(level=20, gems=[(None, [("Wolf Pack", 6)])], config='<Input name="resistancePenalty" number="-10"/>'),
                        stats={"Life": 600})
        self.assertTrue(any("tier 8" in f["motivo"] for f in early["reprovas"] if f["regra"] == "gem"))
        self.assertFalse([f for f in verdict(build_xml(level=20, config='<Input name="resistancePenalty" number="-10"/>'),
                                             stats={"FireResist": -20})["reprovas"] if f["regra"] == "resistência"])
        self.assertTrue([f for f in verdict(build_xml(level=70), stats={"FireResist": 40})["reprovas"] if f["regra"] == "resistência"])
        low = verdict(build_xml(level=70, gems=[(None, [("Wolf Pack", 5)])]))
        self.assertTrue(any("abaixo do tier 8" in f["motivo"] for f in low["reprovas"]))
        high = verdict(build_xml(level=70, gems=[(None, [("Wolf Pack", 18)])]))
        self.assertTrue(any("Wolf Pack nível 18 exige personagem nível 78" in f["motivo"] for f in high["reprovas"]))
        granted = verdict(build_xml(level=70, gems=[("Tree:62743", [("Wild Protector", 20)])]))
        self.assertFalse([f for f in granted["reprovas"] if f["regra"] == "gem"])  # nível da skill concedida vem do nó

    def test_spirit_uniques_league_bases_and_swap_grants(self):
        hysseg = ('<Item id="1">Rarity: UNIQUE\nHysseg\'s Claw\nFamilial Talisman\nItem Level: 82\nImplicits: 1\n'
                  'Minions deal 50% increased Damage\nGrants Skill: Level 20 Cackling Companions\n100% increased Physical Damage\n</Item>')
        club = '<Item id="2">Rarity: RARE\nMaca\nRunemastered Studded Greatclub\nItem Level: 82\nImplicits: 0\n</Item>'
        slots = '<Slot name="Weapon 1" itemId="2"/><Slot name="Weapon 1 Swap" itemId="1"/>'
        bases = {"Runemastered Studded Greatclub": {"name": "Runemastered Studded Greatclub", "level": 55, "liga": True, "oculta": True,
                                                    "tags": frozenset({"mace"}), "socket_limit": 3}}
        xml = build_xml(level=90, items=hysseg + club, slots=slots)
        starter = verdict(xml, trilha="starter", bases=bases)
        degrau = [f["motivo"] for f in starter["reprovas"] if f["regra"] == "gear: degrau"]
        self.assertTrue(any("Hysseg's Claw é unique" in m for m in degrau))
        self.assertTrue(any("é de liga" in m for m in degrau))
        broken = verdict(xml, trilha="desbalanceada", bases=bases)
        self.assertFalse([f for f in broken["reprovas"] if f["regra"] == "gear: degrau"])
        self.assertTrue(any("segundo conjunto de armas" in a and "Cackling Companions" in a for a in broken["avisos"]))
        self.assertTrue(any("é de liga" in a and "VERIFY" in a for a in broken["avisos"]))
        over = verdict(build_xml(level=90), stats={"SpiritUnreserved": -12})
        self.assertIn("spirit", [f["regra"] for f in over["reprovas"]])

    def test_stage_rules_without_engine(self):
        xml = build_xml(level=30, nodes="1,2,3,4,5",
                        gems=[(None, [("Despair", 8)]), (None, [("Enfeeble", 8)]), (None, [("Sniper's Mark", 8)]),
                              (None, [("Explosive Spear", 8)])],
                        config='<Input name="resistancePenalty" number="-60"/><Input name="usePowerCharges" boolean="true"/>')
        xml = xml.replace('<Spec nodes="1,2,3,4,5"/>', '<Spec nodes="1,2,3,4,5"><Sockets><Socket nodeId="5" itemId="0"/></Sockets></Spec>')
        tree = {1: {"kind": "ClassStart", "name": "RANGER"}, 2: {"kind": "Normal", "name": "Dex"},
                3: {"kind": "Notable", "name": "The Catha's Balance", "ascendancy": "Spirit Walker"},
                4: {"kind": "Notable", "name": "Idolatry", "ascendancy": "Spirit Walker"}, 5: {"kind": "Socket", "name": "Jewel Socket"}}
        stats = {"Int": 10, "ReqInt": 20, "ManaPerSecondCost": 50, "ManaRegenRecovery": 10, "ManaUnreserved": 5, "ManaCost": 20,
                 "EnemyCurseLimit": 1, "Life": 500}
        v = verdict(xml, stats=stats, tree=tree, allocated=[1, 2, 3, 4, 5])
        rules = sorted({f["regra"] for f in v["reprovas"]})
        self.assertFalse(v["aprovada"])
        for rule in ("joia", "atributos", "mana", "config", "maldições", "vida"):
            self.assertIn(rule, rules)
        motivos = " ".join(f["motivo"] for f in v["reprovas"])
        self.assertIn("penalidade de resistência -60; a faixa do L30 é -10", motivos)
        self.assertIn("usePowerCharges ligado na config sem produtor", motivos)
        self.assertEqual(v["trilha"], "campanha")
        self.assertEqual(verdict(xml.replace('level="30"', 'level="21"'), stats=stats, tree=tree, allocated=[1, 2, 3, 4, 5])["medidas"]["ascendencia"], "2/0")
        self.assertEqual(v["nota"], 200.0)
        with self.assertRaises(ValueError):
            verdict(xml, trilha="hardcore")

    def test_minion_dps_is_the_score_when_the_player_deals_none(self):
        v = verdict(build_xml(level=90), stats={"CombinedDPS": 0, "TotalEHP": 400}, minion={"TotalDPS": 100})
        self.assertEqual((v["medidas"]["DPS_fonte"], v["nota"]), ("minion (um)", 200.0))


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealJudgeTests(unittest.TestCase):
    """Uma etapa montada no lab e julgada no motor: Int abaixo do exigido pelo Wolf Pack reprova."""

    @classmethod
    def tearDownClass(cls):
        from src.lab import service
        service.handle("close", {})

    def test_low_int_for_wolf_pack_is_rejected(self):
        from src.lab import service
        service.handle("open", {"from": "new", "class": "Huntress", "ascendancy": "Spirit Walker", "level": 70,
                                "weapon": "Hardwood Spear", "name": "juiz real"})
        service.handle("add_skill", {"gems": [["Wolf Pack", 16], ["Feeding Frenzy I", 1]]})
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(service, "EXPORT_DIR", Path(td)):
                out = service.handle("export", {"name": "l70"})
                verdict = service.handle("judge", {"path": out["xml"], "trilha": "starter"})
        etapa = verdict["etapas"][0]
        self.assertFalse(etapa["aprovada"])
        self.assertTrue(any(r.startswith("atributos: Int") for r in etapa["reprovas"]))
        self.assertEqual(etapa["medidas"]["DPS_fonte"], "minion (um)")
        self.assertIn("pontos de passiva sem uso", " ".join(etapa["avisos"]))


if __name__ == "__main__":
    unittest.main()
