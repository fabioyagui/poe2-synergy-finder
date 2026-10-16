"""Testes do laboratório de medição.

A parte pura (parsing, XML, pontuação) roda sempre. A parte que lê os dados do PoB
instalado e a que sobe o motor real são puladas quando a máquina não os tem.
"""
import unittest

from src import pob_engine
from src.lab import engine


def _pob_ready() -> str:
    try:
        return "" if pob_engine.setup_status()["ready"] else "Motor PoB não configurado nesta máquina"
    except Exception as exc:
        return f"diagnóstico do motor falhou: {exc}"


POB_SKIP = _pob_ready()

GEM_XML = ('<Skill><Gem skillId="FallingThunderPlayer" level="5" nameSpec="Falling Thunder"/>'
           '<Gem skillId="SupportX" level="1" nameSpec="X"/></Skill>')


class PureTests(unittest.TestCase):
    def test_gem_level_follows_character_level(self):
        self.assertEqual(engine.gem_level(1), 1)
        self.assertEqual(engine.gem_level(14), 5)
        self.assertEqual(engine.gem_level(26), 8)
        self.assertEqual(engine.gem_level(95), 20)

    def test_with_stat_set_patches_only_the_first_gem(self):
        out = engine.with_stat_set(GEM_XML, 2)
        self.assertIn('<StatSetIndex grantedEffect="FallingThunderPlayer" index="2"/>', out)
        self.assertIn('<StatSetCalcsIndex grantedEffect="FallingThunderPlayer" index="2"/>', out)
        self.assertIn('nameSpec="X"/>', out)

    def test_with_stat_set_targets_a_skill_id(self):
        out = engine.with_stat_set(GEM_XML, 3, skill_id="SupportX")
        self.assertIn('grantedEffect="SupportX" index="3"', out)
        self.assertIn('nameSpec="Falling Thunder"/>', out)
        with self.assertRaises(ValueError):
            engine.with_stat_set(GEM_XML, 1, skill_id="Nope")

    def test_score_is_zero_without_change_and_weighs_log_ratios(self):
        before = {"a": 100, "b": 50}
        self.assertAlmostEqual(engine.score(before, before, {"a": 0.5, "b": 0.5}), 0)
        self.assertGreater(engine.score({"a": 200, "b": 50}, before, {"a": 1}), 0)
        self.assertLess(engine.score({"a": 50, "b": 50}, before, {"a": 1}), 0)
        self.assertAlmostEqual(engine.score({"a": 200, "b": 25}, before, {"a": 1, "b": 1}), 0)

    def test_normal_item_text(self):
        self.assertEqual(engine.normal("Gothic Quarterstaff"), "Rarity: NORMAL\nGothic Quarterstaff\nGothic Quarterstaff")

    def test_max_roll_and_applies_and_item_text(self):
        from src.lab import data
        self.assertEqual(data.max_roll("Adds (1-2) to (4-5) Physical Damage"), "Adds 2 to 5 Physical Damage")
        mod = {"type": "Prefix", "lines": ("+8 to Strength",), "weights": (("ring", 1), ("default", 0))}
        self.assertTrue(data.applies(mod, {"ring", "default"}))
        self.assertFalse(data.applies(mod, {"default"}))
        self.assertFalse(data.applies(mod, {"boots"}))
        base = {"name": "Iron Ring", "implicit": "+1 to Strength\n+2 to Dexterity"}
        text = data.item_text(base, [mod], 15, "MAGIC")
        self.assertEqual(text.splitlines(), ["Rarity: MAGIC", "Plano", "Iron Ring", "Item Level: 15", "Implicits: 2",
                                             "+1 to Strength", "+2 to Dexterity", "+8 to Strength"])


@unittest.skipIf(POB_SKIP, POB_SKIP)
class PobDataTests(unittest.TestCase):
    def test_mods_and_bases_are_read_from_the_installed_pob(self):
        from src.lab import data
        mods = data.load_mods()
        self.assertGreater(len(mods), 1000)
        life = next(m for m in mods if m["id"] == "IncreasedLife1")
        self.assertEqual((life["type"], life["lines"][0], life["level"]), ("Prefix", "+19 to maximum Life", 1))
        self.assertTrue(data.applies(life, {"ring"}))
        staves = data.load_bases("staff.lua")
        self.assertTrue(any(b["name"] == "Wrapped Quarterstaff" and "warstaff" in b["tags"] for b in staves))
        self.assertFalse(any("Runeforged" in b["name"] for b in data.load_bases("body.lua")))

    def test_weapon_for_picks_the_highest_base_the_level_allows(self):
        from src.lab import data
        self.assertEqual(data.weapon_for("Quarterstaff", 1), "Long Quarterstaff")  # sem requisito de nível e mais dano que a Wrapped
        self.assertEqual(data.weapon_for("Quarterstaff", 14), "Gothic Quarterstaff")
        self.assertIsNone(data.weapon_for("Elemental", 14))

    def test_quality_effects_include_the_gemling_additional_effect(self):
        from src.lab import data
        q = data.quality_effects()
        self.assertGreater(len(q), 150)
        self.assertIn(("charge_skip_consume_chance_%", 1.0), q["Falling Thunder"]["additional"])
        self.assertIn(("active_skill_fire_damage_+%_final", 2.5), q["Living Bomb"]["additional"])


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealEngineTests(unittest.TestCase):
    """A âncora do Monk, medida de verdade: Power Charges multiplicam o Falling Thunder por 5 e dão 9 projéteis."""

    @classmethod
    def setUpClass(cls):
        cls.lab = engine.Lab()

    @classmethod
    def tearDownClass(cls):
        cls.lab.close()

    def test_falling_thunder_anchor_is_measured(self):
        from src.lab import bench
        rows = bench.verify_anchor(self.lab, "Quarterstaff", "Falling Thunder", 14)
        charged = [r for r in rows if r["cond"] == "cargas (3 de cada)"]
        self.assertEqual(len(charged), 1)
        self.assertEqual(charged[0]["proj"], 9)
        self.assertGreaterEqual(charged[0]["mult"], 4.5)
        self.assertFalse(charged[0]["generic"])

    def test_skill_parts_stop_when_parts_run_out(self):
        from src.lab import bench
        _group, xml = bench.minimal_build(self.lab, "Monk", 14, "Gothic Quarterstaff", "Killing Palm")
        parts = bench.skill_parts(self.lab, xml, bench.enemy_config(14))
        self.assertEqual(len(parts), 1)
        self.assertGreater(parts[0]["AverageDamage"], 0)
