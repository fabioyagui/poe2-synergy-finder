import unittest
from src.pob_bridge import parse_build

XML = """<PathOfBuilding2>
  <Build level="93" className="Mercenary" ascendClassName="Gemling Legionnaire">
    <PlayerStat stat="Life" value="2495"/>
  </Build>
  <Items activeItemSet="1">
    <Item id="1">Rarity: RARE
Solar Needle
Rattling Sceptre
--------
+20 to Strength</Item>
    <Item id="2">Rarity: UNIQUE
The Burning Monolith
Heavy Belt
--------
+100 to maximum Life</Item>
    <ItemSet id="1">
      <Slot name="Weapon 1" itemId="1"/>
      <Slot name="Belt" itemId="2"/>
      <Slot name="Helmet" itemId="0"/>
    </ItemSet>
  </Items>
  <Skills activeSkillSet="1">
    <SkillSet id="1">
      <Skill enabled="true" label="Oil Grenade" mainActiveSkill="1">
        <Gem enabled="true" nameSpec="Oil Grenade" level="20"/>
      </Skill>
    </SkillSet>
  </Skills>
  <Config activeConfigSet="1">
    <ConfigSet id="1">
      <Input name="conditionBoss" value="true"/>
      <Input name="multiplierWitheredStackCount" value="10"/>
    </ConfigSet>
  </Config>
</PathOfBuilding2>"""

XML_POSITIONAL = """<PathOfBuilding2>
  <Build level="1"/>
  <Items activeItemSet="1">
    <Item>Rarity: RARE
First Item
Base A</Item>
    <Item>Rarity: UNIQUE
Second Item
Base B</Item>
    <ItemSet id="1"><Slot name="Ring 1" itemId="2"/></ItemSet>
  </Items>
</PathOfBuilding2>"""

class PobV10Tests(unittest.TestCase):
    def test_equipped_items_are_resolved_from_itemset_slots(self):
        d = parse_build(XML, "fixture")
        self.assertEqual(d["items"]["count"], 2)
        self.assertEqual(d["items"]["defined_count"], 2)
        self.assertEqual(d["items"]["slots"][0]["slot"], "Weapon 1")
        self.assertEqual(d["items"]["slots"][0]["item"]["name"], "Solar Needle")
        self.assertEqual(d["items"]["slots"][1]["item"]["name"], "The Burning Monolith")

    def test_zero_item_slot_is_not_counted(self):
        d = parse_build(XML, "fixture")
        self.assertNotIn("Helmet", [x["slot"] for x in d["items"]["slots"]])

    def test_positional_fallback(self):
        d = parse_build(XML_POSITIONAL, "fixture")
        self.assertEqual(d["items"]["slots"][0]["item"]["name"], "Second Item")


    def test_trade_lines_skip_pob_descriptors_and_keep_rendered_roll(self):
        xml = """<PathOfBuilding2><Build level="1"/><Items activeItemSet="1">
        <Item id="1">Rarity: RARE
Range Test
Heavy Belt
--------
Item Level: 80
--------
{ Prefix Modifier "Healthy" (Tier: 3) — Life }
+95(90-99) to maximum Life
{range:0.5}+20 to Strength
Prefix: IncreasedLife7</Item>
        <ItemSet id="1"><Slot name="Belt" itemId="1"/></ItemSet></Items></PathOfBuilding2>"""
        d=parse_build(xml,'fixture')
        lines=d['items']['slots'][0]['item']['trade_lines']
        self.assertEqual(lines,['+95(90-99) to maximum Life','+20 to Strength'])

    def test_config_is_preserved(self):
        d = parse_build(XML, "fixture")
        self.assertEqual(d["config"]["values"]["conditionBoss"], "true")
        self.assertEqual(d["config"]["values"]["multiplierWitheredStackCount"], "10")

if __name__ == "__main__":
    unittest.main()
