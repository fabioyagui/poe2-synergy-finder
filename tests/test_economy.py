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


AUGMENT_TEXT = """
return {
	["Lesser Iron Rune"] = {
		["weapon"] = {
				type = "Rune",
				"14% increased Physical Damage",
				"Bonded: 20% increased effect of Fully Broken Armour",
				statOrder = { 830, 5236 },
				isSocketBound = false,
				rank = { 0 },
		},
		["armour"] = {
				type = "Rune",
				"14% increased Armour, Evasion and Energy Shield",
				statOrder = { 854 },
				isSocketBound = false,
				rank = { 0 },
		},
	},
	["Tzamoto's Soul Core of Ferocity"] = {
		["helmet"] = {
				type = "SoulCore",
				"+(2-4) to Maximum Rage",
				statOrder = { 1 },
				isSocketBound = false,
				rank = { 50 },
		},
	},
	["Idol of Alira"] = {
		["gloves"] = {
				type = "Idol",
				"Bonded: +1 to Maximum Power Charges",
				statOrder = { 2 },
				isSocketBound = false,
				rank = { 50 },
		},
	},
	["Amanamu's Gaze"] = {
		["helmet"] = {
				type = "AbyssalEye",
				"+2 to Armour per 1 Spirit",
				statOrder = { 3 },
				isSocketBound = false,
				rank = { 50 },
		},
	},
}
"""

TIMELESS_TEXT = """
return {
	["additions"] = {
		{
			["dn"] = "Fire Damage",
			["id"] = "vaal_small_fire_damage",
			["sd"] = {
				"(7-12)% increased Fire Damage",
			},
		},
	},
	["nodes"] = {
		{
			["dn"] = "Black Scythe Training",
			["id"] = "kalguur_keystone_1",
			["ks"] = true,
			["not"] = false,
			["sd"] = {
				"Gain no inherent bonus from Strength",
				"1% increased Energy Shield per 2 Strength",
			},
		},
		{
			["dn"] = "Buried Animosity",
			["id"] = "abyss_notable_3",
			["ks"] = false,
			["not"] = true,
			["sd"] = {
				"+1 to Maximum Rage per 50 Tribute",
			},
		},
	},
}
"""

JEWEL_UNIQUE_TEXT = """
return {
[[
Controlled Metamorphosis
Diamond
Limited to: 1
Radius: Variable
Passives in Radius can be Allocated without being connected to your tree
-(20-5)% to all Elemental Resistances
]],[[
Heroic Tragedy
Timeless Jewel
Limited to: 1 Historic
Radius: Very Large
Passives in radius are Conquered by the Kalguur
Historic
]],
}
"""

JEWEL_MODS = [
    {"id": "JewelRage", "type": "Prefix", "lines": ("+2 to Maximum Rage",), "level": 1, "group": "MaxRage",
     "weights": (("strjewel", 1), ("jewel", 0))},
    {"id": "JewelRadiusRage", "type": "Prefix", "lines": ("+1 to Maximum Rage",), "level": 1, "group": "MaxRage",
     "weights": (("str_radius_jewel", 1), ("jewel", 0))},
    {"id": "JewelRadiusLarge", "type": "Prefix", "lines": ("Upgrades Radius to Large",), "level": 1, "group": "Larger",
     "weights": (("radius_jewel", 1), ("jewel", 0))},
    {"id": "JewelDisabled", "type": "Suffix", "lines": ("nothing",), "level": 1, "group": "Off",
     "weights": (("intjewel", 0), ("jewel", 0))},
]


class JewelAndAugmentRecordTests(unittest.TestCase):
    def test_augments_are_parsed_per_slot_with_bonded_lines_kept(self):
        from src.lab import data
        parsed = data.parse_augments_text(AUGMENT_TEXT)
        self.assertEqual([(a["name"], a["type"]) for a in parsed],
                         [("Lesser Iron Rune", "Rune"), ("Tzamoto's Soul Core of Ferocity", "SoulCore"),
                          ("Idol of Alira", "Idol"), ("Amanamu's Gaze", "AbyssalEye")])
        self.assertEqual(parsed[0]["slots"]["weapon"],
                         ["14% increased Physical Damage", "Bonded: 20% increased effect of Fully Broken Armour"])
        self.assertEqual(parsed[1]["slots"]["helmet"], ["+4 to Maximum Rage"])  # teto da faixa

    def test_augment_records_have_kind_socket_note_and_degrau(self):
        from src.lab import data
        records = economy.records_from_augments(data.parse_augments_text(AUGMENT_TEXT))
        self.assertEqual([r["kind"] for r in records], ["RUNE", "SOUL_CORE", "IDOL", "AUGMENT"])
        rune = records[0]
        self.assertEqual((rune["owner"], rune["tags"], rune["source"]),
                         ("weapon, armour", ["weapon", "armour"], "ModRunes.lua"))
        self.assertEqual(rune["note"], economy.SOCKET_NOTE)
        self.assertEqual([r["degrau"] for r in records], [1, 3, 3, 4])
        self.assertEqual(records[3]["tags"][0], "AbyssalEye")

    def test_timeless_passives_are_one_record_per_passive_and_only_for_jewels_in_the_game(self):
        from src.lab import data
        passives = data.parse_timeless_text(TIMELESS_TEXT)
        self.assertEqual([(p["legion"], p["kind"]) for p in passives],
                         [("vaal", "small"), ("kalguur", "keystone"), ("abyss", "notable")])
        records = economy.records_from_timeless(passives)
        self.assertEqual([r["name"] for r in records],
                         ["Black Scythe Training (Heroic Tragedy)", "Buried Animosity (Undying Hate)"])
        self.assertEqual((records[0]["kind"], records[0]["owner"], records[0]["radius"], records[0]["degrau"]),
                         ("TIMELESS", "Heroic Tragedy", "Very Large", 4))
        self.assertEqual(records[0]["note"], economy.RADIUS_NOTE)

    def test_jewel_mods_split_rare_and_time_lost_even_in_the_same_group(self):
        records = economy.records_from_jewel_mods(JEWEL_MODS)
        self.assertEqual([(r["kind"], r["name"]) for r in records],
                         [("JEWEL_MOD", "Prefix: +2 to Maximum Rage"),
                          ("TIME_LOST", "Time-Lost Prefix in Radius: +1 to Maximum Rage"),
                          ("TIME_LOST", "Time-Lost Prefix in Radius: Upgrades Radius to Large")])
        self.assertEqual(records[0]["owner"], "Ruby")
        self.assertNotIn("radius", records[0])
        self.assertEqual((records[1]["owner"], records[1]["degrau"]), ("Time-Lost Ruby", 4))
        self.assertTrue(records[1]["radius"])
        self.assertEqual(records[1]["note"], economy.RADIUS_NOTE)

    def test_unique_jewels_become_jewel_unique_with_radius(self):
        from src.lab import data
        uniques = data.parse_uniques_text(JEWEL_UNIQUE_TEXT)
        self.assertEqual(uniques[1]["lines"], ["Passives in radius are Conquered by the Kalguur"])
        records = economy.records_from_uniques(uniques)
        self.assertEqual([(r["kind"], r["radius"]) for r in records],
                         [("JEWEL_UNIQUE", "Variable"), ("JEWEL_UNIQUE", "Very Large")])
        plain = economy.records_from_uniques([{"name": "Andvarius", "base": "Gold Ring", "lines": ["+10 to Dexterity"]}])
        self.assertEqual((plain[0]["kind"], plain[0]["degrau"]), ("UNIQUE", 4))
        self.assertNotIn("radius", plain[0])

    def test_item_text_without_markup_still_finds_tagged_resources(self):
        record = economy.records_from_augments(
            [{"name": "X", "type": "SoulCore", "slots": {"helmet": ["+4 to Maximum Rage"]}}])[0]
        self.assertIn(("rage", "UNLOCKS"), {(e["resource"], e["verb"]) for e in economy.edges_for(record)})
        convert = economy.records_from_augments(
            [{"name": "Y", "type": "SoulCore", "slots": {"weapon": ["Convert 20% of Requirements to Strength",
                                                                    "+40% of Armour also applies to Cold Damage"]}}])[0]
        verbs = {(e["resource"], e["verb"]) for e in economy.edges_for(convert)}
        self.assertIn(("strength", "CONVERTS"), verbs)
        self.assertIn(("armour", "CONVERTS"), verbs)
        # Texto do catálogo (com marcação) não muda: "rage" sem tag continua fora.
        gem = economy.record_from_entity(entity("Gem", "SKILL", "+4 to Maximum Rage"))
        self.assertEqual(economy.edges_for(gem), [])

    def test_kind_groups_filter_anchors_and_lookup(self):
        from src.lab import data
        records = (economy.records_from_augments(data.parse_augments_text(AUGMENT_TEXT))
                   + economy.records_from_jewel_mods(JEWEL_MODS)
                   + economy.records_from_uniques(data.parse_uniques_text(JEWEL_UNIQUE_TEXT))
                   + economy.records_from_timeless(data.parse_timeless_text(TIMELESS_TEXT))
                   + [economy.record_from_entity(entity(
                       "Idolatry", "ASCENDANCY_NODE",
                       "Companions deal 10% increased damage per [Idol] in your Equipment", ascendancy="Spirit Walker"))])
        m = economy.EconomyMap(records, {"source": "fixture"})
        self.assertEqual(economy.expand_kinds(["jewels", "RUNE"]), economy.JEWEL_KINDS | {"RUNE"})
        anchors = m.anchors(kinds=["AUGMENTS"])["results"]
        self.assertEqual({(a["kind"], a["resource"], a["verb"]) for a in anchors},
                         {("SOUL_CORE", "rage", "UNLOCKS"), ("IDOL", "power charge", "UNLOCKS")})
        self.assertEqual(anchors[0]["note"], economy.SOCKET_NOTE)
        jewels = m.anchors(kinds=["JEWELS"])["results"]
        self.assertEqual({a["kind"] for a in jewels}, {"JEWEL_MOD", "TIME_LOST", "JEWEL_UNIQUE", "TIMELESS"})
        time_lost = next(a for a in jewels if a["kind"] == "TIME_LOST")
        self.assertEqual((time_lost["note"], time_lost["degrau"]), (economy.RADIUS_NOTE, 4))
        metamorphosis = next(a for a in jewels if a["name"] == "Controlled Metamorphosis")
        self.assertEqual((metamorphosis["resource"], metamorphosis["verb"]), ("passive", "UNLOCKS"))
        idol = m.lookup("Idol")
        self.assertEqual({(r["kind"], r["name"]) for r in idol["results"]},
                         {("IDOL", "Idol of Alira"), ("ASCENDANCY_NODE", "Idolatry")})
        self.assertEqual(next(r for r in idol["results"] if r["kind"] == "IDOL")["item"], "gloves")
        radius = m.lookup("Radius", kinds=["JEWELS"])
        self.assertEqual({r["kind"] for r in radius["results"]}, {"TIME_LOST", "JEWEL_UNIQUE"})
        self.assertEqual(m.status()["records_by_kind"]["TIME_LOST"], 2)
        self.assertIn("JEWELS", m.status()["kind_groups"])


class PairTests(unittest.TestCase):
    """Interação skill -> skill: uma cria a entidade, outra a lê/consome/replica com 'more'."""

    @classmethod
    def setUpClass(cls):
        cls.map = economy.EconomyMap.from_entities([
            entity("Whirling Slash", "SKILL", "Perform a circular slash that kicks up a Whirlwind around you.", "Maximum 3 stages"),
            entity("Whirlwind Lance", "SKILL", "Consumes a Frenzy Charge if possible to create the Whirlwind with one more stage"),
            entity("Twister", "SKILL",
                   "Consumes Whirlwinds to create an additional twister and deal 80% more damage per Whirlwind stage",
                   "Twister duration is 3 seconds"),
            entity("Flicker Strike", "SKILL", "Strikes 2 additional times per Power Charge"),
            entity("Lone", "SKILL", "40% more Damage against [Shock|Shocked] enemies"),
        ], {"source": "fixture"})

    def test_skill_created_entities_are_resources(self):
        verbs = {(e["resource"], e["verb"]) for r in self.map.records if r["name"] == "Whirling Slash" for e in economy.edges_for(r)}
        self.assertIn(("whirlwind", "PRODUCES"), verbs)
        twister = {(e["resource"], e["verb"]) for r in self.map.records if r["name"] == "Twister" for e in economy.edges_for(r)}
        self.assertIn(("whirlwind", "CONSUMES"), twister)
        self.assertIn(("whirlwind", "REPLICATES"), twister)

    def test_pairs_join_producer_and_anchor_from_different_skills(self):
        out = self.map.pairs("whirlwind")
        self.assertTrue(out["ok"])
        row = out["results"][0]
        self.assertEqual((row["anchor"]["name"], row["anchor"]["verb"], row["score"], row["self_loop"]),
                         ("Twister", "REPLICATES", 5, False))
        self.assertEqual({p["name"] for p in row["producers"]}, {"Whirling Slash", "Whirlwind Lance"})
        self.assertEqual(row["producer_slots"], {"SKILL": 2})

    def test_anchor_without_producer_is_listed_apart(self):
        out = self.map.pairs()
        names = {w["anchor"]["name"] for w in out["anchors_without_producer"]}
        self.assertIn("Flicker Strike", names)  # ninguém produz Power Charge na fixture
        self.assertEqual([r["anchor"]["name"] for r in out["results"]], ["Twister"])
        self.assertFalse(self.map.pairs("nonexistent")["ok"])


class MagnitudeTests(unittest.TestCase):
    """Famílias de poder que não citam um recurso do léxico (porte do PoE 1 + Gemling no PoE 2)."""

    def edges(self, original, kind="ASCENDANCY_NODE"):
        record = economy.record_from_entity(entity("X", kind, original, ascendancy="Gemling Legionnaire"))
        return {(e["resource"], e["verb"]): e for e in economy.edges_for(record)}

    def test_gemling_nodes_are_no_longer_zero(self):
        cases = {
            "Gem Quality grants Socketed Skills an additional effect": ("gem quality", "AMPLIFIES", 3),
            "+2% to Quality of all Skills": ("gem quality", "AMPLIFIES", 1.5),
            "+2 to Level of all Skills with an Intelligence requirement": ("gem levels", "AMPLIFIES", 2),
            "Skills deal 20% increased Damage per Connected Red Support Gem": ("support gems", "READS", 2),
            "+1% to Maximum Fire Resistance per 3 Red Support Gems Socketed": ("support gems", "READS", 1),  # defesa: metade
            "Grants Skill: Virtuous Barrier": ("granted skill", "UNLOCKS", 2),
        }
        for text, (resource, verb, score) in cases.items():
            with self.subTest(text=text):
                edge = self.edges(text).get((resource, verb))
                self.assertIsNotNone(edge)
                self.assertEqual(economy.EconomyMap._anchor_score(edge, False), score)

    def test_poe1_families_still_match(self):
        self.assertIn(("damage as extra", "CONVERTS"), self.edges("Gain 4% of Physical Damage as extra Chaos Damage"))
        self.assertIn(("additional projectiles", "REPLICATES"), self.edges("Skills fire an additional Projectile"))
        self.assertIn(("resistance overcap", "READS"),
                      self.edges("8% increased Elemental Damage per 1% Fire Resistance above 75%"))

    def test_plain_level_and_quality_lines_do_not_overmatch(self):
        self.assertFalse({k for k in self.edges("Gain 10 Mana per Level") if k[0] in ("gem levels", "gem quality")})
        self.assertFalse({k for k in self.edges("20% increased Quality of Flasks") if k[0] == "gem quality"})


if __name__ == "__main__":
    unittest.main()
