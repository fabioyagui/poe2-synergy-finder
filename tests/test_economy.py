import unittest

from src import economy


def entity(name, kind, *originals, ascendancy="", availability="released"):
    return {
        "id": name.lower().replace(" ", "-"), "name": name, "kind": kind, "ascendancy": ascendancy,
        "availability": availability, "tags": [],
        "texts": [{"original": text, "text": economy.parse_markup(text)[0]} for text in originals],
    }


ENTITIES = [
    entity("Flicker Strike", "SKILL", "Teleports and [Strike|Strikes] 2 additional times per Power Charge, with 285% more [Attack] Speed"),
    entity("Glacial Cascade", "SKILL",
           "[Consume|Consumes] [Freeze] on enemies to deal 250% more Damage",
           "Deals 10 to 20 [Cold] Damage", "Deals 30 to 40 [Cold] Damage"),
    entity("Conduit", "SUPPORT", "Supported Skills deal 40% more Damage against [Shock|Shocked] enemies"),
    entity("Charged Mind", "NOTABLE", "25% chance to [Gain|gain] a Power Charge on [Critical|Critical Hit]"),
    entity("Overcharge", "NOTABLE", "+1 to Maximum Power Charges"),
    entity("Vitality", "PASSIVE", "3% increased maximum Life"),
    entity("Vitality", "PASSIVE", "3% increased maximum Life"),
    entity("Storm Focus", "ASCENDANCY_NODE", "30% more Damage per Power Charge", ascendancy="Stormweaver"),
    entity("Fury", "ASCENDANCY_NODE", "[Gain] 5 [Rage] on [Hit]", ascendancy="Titan"),
    entity("Unused", "SKILL", "[DNT] 50% more Damage per Power Charge"),
    entity("Hidden", "SKILL", "50% more Damage per Power Charge", availability="unreleased"),
    entity("Decoration", "TREE_DECORATION", "50% more Damage per Power Charge"),
]


class MarkupTests(unittest.TestCase):
    def test_markup_is_removed_and_spans_point_at_the_shown_text(self):
        clean, spans = economy.parse_markup("[Gain] 5 [Rage] against [Shock|Shocked] enemies")
        self.assertEqual(clean, "Gain 5 Rage against Shocked enemies")
        self.assertEqual([(tag, clean[s:e]) for tag, s, e in spans],
                         [("Gain", "Gain"), ("Rage", "Rage"), ("Shock", "Shocked")])

    def test_plain_resources_are_found_without_tags(self):
        found = economy.mentions("30% more Damage per Power Charge", [])
        self.assertEqual([name for name, _s, _e in found], ["power charge"])


class VerbTests(unittest.TestCase):
    def verbs(self, original):
        record = economy.record_from_entity(entity("X", "SKILL", original))
        return {(e["resource"], e["verb"]) for e in economy.edges_for(record)}

    def test_per_resource_with_additional_effect_replicates(self):
        self.assertIn(("power charge", "REPLICATES"), self.verbs("Strikes 2 additional times per Power Charge"))

    def test_more_damage_per_resource_reads(self):
        self.assertIn(("power charge", "READS"), self.verbs("30% more Damage per Power Charge"))

    def test_consume_and_gain(self):
        self.assertIn(("freeze", "CONSUMES"), self.verbs("[Consume|Consumes] [Freeze] on enemies to deal 250% more Damage"))
        self.assertIn(("rage", "PRODUCES"), self.verbs("[Gain] 5 [Rage] on [Hit]"))

    def test_participle_reads_the_state(self):
        self.assertIn(("shock", "READS"), self.verbs("40% more Damage against [Shock|Shocked] enemies"))

    def test_maximum_unlocks_stacks_but_not_pools(self):
        self.assertIn(("power charge", "UNLOCKS"), self.verbs("+1 to Maximum Power Charges"))
        self.assertEqual(self.verbs("3% increased maximum Life"), {("life", "AMPLIFIES")})

    def test_cannot_limits(self):
        self.assertIn(("rage", "LIMITS"), self.verbs("Cannot gain [Rage] while using this Skill"))


class MapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map = economy.EconomyMap.from_entities(ENTITIES, {"source": "fixture"})

    def test_unusable_entities_are_dropped(self):
        names = {r["name"] for r in self.map.records}
        self.assertFalse(names & {"Unused", "Hidden", "Decoration"})

    def test_gem_level_variants_collapse_to_one_line(self):
        cascade = next(r for r in self.map.records if r["name"] == "Glacial Cascade")
        self.assertEqual(cascade["lines"].count("Deals 30 to 40 Cold Damage"), 1)
        self.assertNotIn("Deals 10 to 20 Cold Damage", cascade["lines"])

    def test_anchor_ranking_follows_the_method(self):
        results = self.map.anchors()["results"]
        score = {r["name"]: r["score"] for r in results}
        self.assertEqual(results[0]["name"], "Flicker Strike")
        self.assertEqual(score["Flicker Strike"], 5)
        self.assertEqual(score["Storm Focus"], 4)
        self.assertEqual(score["Glacial Cascade"], 3.5)
        self.assertEqual(score["Overcharge"], 2)
        self.assertNotIn("Fury", score)

    def test_anchor_reports_scaling_of_its_resource(self):
        flicker = next(r for r in self.map.anchors()["results"] if r["name"] == "Flicker Strike")
        self.assertEqual(flicker["scaling"]["producers"], 1)
        self.assertEqual(flicker["scaling"]["unlocks"], 1)
        self.assertEqual(flicker["scaling"]["producer_slots"], {"NOTABLE": 1})

    def test_by_resource_counts_distinct_anchors(self):
        by_resource = {r["resource"]: r["anchors"] for r in self.map.anchors()["by_resource"]}
        self.assertEqual(by_resource["power charge"], 3)

    def test_other_ascendancies_are_hidden(self):
        names = {r["name"] for r in self.map.anchors(ascendancy="Titan")["results"]}
        self.assertNotIn("Storm Focus", names)
        self.assertIn("Flicker Strike", names)

    def test_universal_resources_need_an_explicit_request(self):
        self.assertFalse(any(r["resource"] == "life" for r in self.map.anchors(include_plain_reads=True)["results"]))

    def test_resource_lists_connectors(self):
        out = self.map.resource("power", verbs=["PRODUCES", "UNLOCKS"])
        self.assertEqual(out["resource"]["resource"], "power charge")
        self.assertEqual(set(out["by_verb"]), {"PRODUCES", "UNLOCKS"})
        self.assertEqual(out["by_verb"]["PRODUCES"]["edges"][0]["name"], "Charged Mind")

    def test_unknown_resource_is_an_error_not_an_empty_answer(self):
        self.assertFalse(self.map.resource("nonexistent")["ok"])
        self.assertFalse(self.map.anchors(resource="nonexistent")["ok"])

    def test_lookup_returns_text_and_detected_resources(self):
        out = self.map.lookup("glacial")
        self.assertEqual(out["total"], 1)
        self.assertIn({"resource": "freeze", "verb": "CONSUMES"}, out["results"][0]["resources"])

    def test_status_lists_resources_by_category(self):
        status = self.map.status()
        self.assertIn("power charge", status["resources_by_category"]["stack"])
        self.assertEqual(status["meta"], {"source": "fixture"})


class AxisTests(unittest.TestCase):
    def test_buildup_text_is_not_an_anchor(self):
        self.assertEqual(economy.axis_of("Pins Enemies as though dealing 600% more Damage"), "acumulo")
        self.assertEqual(economy.axis_of("Mark a target, making them more susceptible to being Frozen."), "acumulo")
        self.assertEqual(economy.axis_of("50% more Stun buildup"), "acumulo")
        m = economy.EconomyMap.from_entities([
            entity("Artillery Ballista", "SKILL", "[Pinned|Pins] Enemies as though dealing 600% more Damage"),
        ])
        self.assertEqual(m.anchors(include_plain_reads=True)["results"], [])

    def test_defence_multiplier_scores_half_and_is_tagged(self):
        self.assertEqual(economy.axis_of("Gain an additional 4 Guard per ten Strength if Heavily Stunning"), "defesa")
        self.assertEqual(economy.axis_of("30% more Damage per Power Charge"), "dano")
        m = economy.EconomyMap.from_entities([
            entity("Vanguard I", "SUPPORT", "Gain an additional 4 [Guard] per ten [Strength] if Heavily Stunning"),
            entity("Flicker Strike", "SKILL", "Strikes 2 additional times per Power Charge"),
        ])
        rows = {r["name"]: r for r in m.anchors()["results"]}
        self.assertEqual((rows["Flicker Strike"]["score"], rows["Flicker Strike"]["axis"]), (5, "dano"))
        self.assertEqual((rows["Vanguard I"]["score"], rows["Vanguard I"]["axis"]), (2.5, "defesa"))

    def test_stages_are_scoped_to_their_skill(self):
        m = economy.EconomyMap.from_entities([
            entity("Flameblast", "SKILL", "75% more damage per Stage", "10 maximum Stages"),
            entity("Wind Dancer", "SKILL", "10% more [Evasion] Rating per stage"),
        ])
        self.assertIn("stage (Flameblast)", m.resources)
        self.assertIn("stage (Wind Dancer)", m.resources)
        self.assertNotIn("stage", m.resources)
        self.assertEqual(m.resources["stage (Flameblast)"]["category"], "stack")
        self.assertEqual(m.resources["stage (Flameblast)"]["paga_em"], ["dano"])
        self.assertEqual(m.resources["stage (Wind Dancer)"]["paga_em"], ["defesa"])

    def test_sinks_per_axis_count_distinct_records(self):
        m = economy.EconomyMap.from_entities([
            entity("A", "SKILL", "30% more Damage per Power Charge"),
            entity("B", "NOTABLE", "20% more [Armour] per Power Charge"),
            entity("C", "NOTABLE", "Consume a Power Charge to deal 40% more Damage"),
        ])
        row = m.resources["power charge"]
        self.assertEqual((row["sinks_dano"], row["sinks_defesa"], row["paga_em"]), (2, 1, ["dano", "defesa"]))


UNIQUE_TEXT = '''
-- Item data (c) Grinding Gear Games

return {
-- Staff
[[
Taryn's Shiver
Gelid Staff
League: Dawn of the Hunt
Requires Level 40
Variant: Pre 0.4.0
Variant: Current
Implicits: 1
{tags:cold}+(20-30)% to Cold Resistance
{variant:1}(60-80)% increased Spell Damage
{variant:2}(80-120)% increased Spell Damage
{tags:cold}Gain (30-50)% of Damage as Extra Cold Damage
Consume a Power Charge if able to deal 40% more Damage
]],[[
Andvarius
Gold Ring
Implicits: 1
(6-15)% increased Rarity of Items found
+10 to Dexterity
]],[[
Voll's Protector
{variant:1}Ironclad Vestments
{variant:2}Gilded Vest
Variant: Pre 0.5.0
Variant: Current
Implicits: 0
25% chance to gain a Power Charge on Critical Hit
]],
}
'''


class PobItemRecordTests(unittest.TestCase):
    def test_unique_text_keeps_current_variant_and_max_roll(self):
        from src.lab import data
        parsed = data.parse_uniques_text(UNIQUE_TEXT)
        self.assertEqual([u["name"] for u in parsed], ["Taryn's Shiver", "Andvarius", "Voll's Protector"])
        self.assertEqual((parsed[2]["base"], parsed[2]["lines"]), ("Gilded Vest", ["25% chance to gain a Power Charge on Critical Hit"]))
        taryn = parsed[0]
        self.assertEqual((taryn["base"], taryn["league"]), ("Gelid Staff", "Dawn of the Hunt"))
        self.assertEqual(taryn["lines"], ["+30% to Cold Resistance", "120% increased Spell Damage",
                                          "Gain 50% of Damage as Extra Cold Damage",
                                          "Consume a Power Charge if able to deal 40% more Damage"])
        self.assertEqual(parsed[1]["lines"], ["15% increased Rarity of Items found", "+10 to Dexterity"])

    def test_uniques_and_mods_become_records_and_anchors(self):
        from src.lab import data
        uniques = data.parse_uniques_text(UNIQUE_TEXT)
        mods = [
            {"id": "PowerChargeMax1", "type": "Suffix", "lines": ("+1 to Maximum Power Charges",), "level": 30,
             "group": "MaxPower", "weights": (("amulet", 1), ("default", 0))},
            {"id": "Life1", "type": "Prefix", "lines": ("+19 to maximum Life",), "level": 1, "group": "Life",
             "weights": (("body_armour", 1), ("default", 0))},
            {"id": "Life2", "type": "Prefix", "lines": ("+29 to maximum Life",), "level": 6, "group": "Life",
             "weights": (("body_armour", 1), ("default", 0))},
            {"id": "Unused", "type": "Prefix", "lines": ("nothing",), "level": 1, "group": "X", "weights": (("default", 0),)},
        ]
        records = economy.records_from_uniques(uniques) + economy.records_from_mods(mods)
        self.assertEqual([r["kind"] for r in records], ["UNIQUE", "UNIQUE", "UNIQUE", "MOD", "MOD"])
        life = next(r for r in records if r["id"] == "mod:Life2")
        self.assertEqual((life["name"], life["owner"]), ("Prefix: +29 to maximum Life", "body_armour"))
        m = economy.EconomyMap(records, {}, {"Taryn's Shiver": {"additional": [("x", 1.0)]}})
        anchors = m.anchors(kinds=["UNIQUE"])["results"]
        self.assertEqual(anchors[0]["name"], "Taryn's Shiver")
        self.assertEqual((anchors[0]["score"], anchors[0]["item"], anchors[0]["quality_additional"]), (3.5, "Gelid Staff", ["x 1/1%"]))
        connectors = m.resource("power charge", verbs=["UNLOCKS"])["by_verb"]["UNLOCKS"]["edges"]
        self.assertEqual([(c["kind"], c["item"]) for c in connectors], [("MOD", "amulet")])


if __name__ == "__main__":
    unittest.main()
