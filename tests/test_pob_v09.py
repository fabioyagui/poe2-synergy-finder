import base64
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from src.pob_bridge import decode_payload, parse_build, _is_zlib_wrapped

XML = """<PathOfBuilding2>
  <Build level="93" className="Mercenary" ascendClassName="Gemling Legionnaire" mainSocketGroup="2">
    <PlayerStat stat="Life" value="2495"/>
    <PlayerStat stat="Mana" value="1388"/>
    <PlayerStat stat="TotalDPS" value="6555.25"/>
  </Build>
  <Tree activeSpec="1">
    <Spec id="1" nodes="10,20,30,40" ascendancyInternalId="Mercenary2"/>
  </Tree>
  <Skills activeSkillSet="1">
    <SkillSet id="1">
      <Skill enabled="true" label="Oil setup" mainActiveSkill="1">
        <Gem enabled="true" nameSpec="Oil Grenade" level="20" quality="20"/>
        <Gem enabled="true" nameSpec="Short Fuse II" level="3" quality="0"/>
      </Skill>
      <Skill enabled="true" label="Flameblast" mainActiveSkill="1">
        <Gem enabled="true" nameSpec="Flameblast" level="20" quality="20"/>
        <Gem enabled="true" nameSpec="Ignite III" level="3" quality="0"/>
      </Skill>
    </SkillSet>
  </Skills>
  <Items activeItemSet="1">
    <ItemSet id="1">
      <Item id="1">Rarity: Rare
Test Staff
Quarterstaff</Item>
    </ItemSet>
  </Items>
</PathOfBuilding2>"""

class PobBridgeTests(unittest.TestCase):
    def test_parse_xml(self):
        d = parse_build(XML, "fixture")
        self.assertEqual(d["level"], 93)
        self.assertEqual(d["ascendancy"], "Gemling Legionnaire")
        self.assertEqual(d["tree"]["allocated_nodes"], 4)
        self.assertEqual(d["tree"]["base_hashes"], ["10","20","30","40"])
        self.assertEqual(d["skill_group_count"], 2)
        self.assertEqual(d["skills"][0]["main_gem"], "Oil Grenade")
        self.assertEqual(d["skills"][1]["gems"][1]["name"], "Ignite III")
        self.assertEqual(d["player_stats"]["Life"], 2495)
        self.assertEqual(d["player_stats"]["TotalDPS"], 6555.25)
        self.assertEqual(d["items"]["count"], 1)

    def test_zlib_code_roundtrip(self):
        raw = zlib.compress(XML.encode("utf-8"))
        code = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        self.assertEqual(decode_payload(code), XML)

    def test_raw_deflate_roundtrip(self):
        obj = zlib.compressobj(wbits=-15)
        raw = obj.compress(XML.encode("utf-8")) + obj.flush()
        code = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        self.assertEqual(decode_payload(code), XML)

    def test_reject_poe1(self):
        with self.assertRaises(ValueError):
            decode_payload("<PathOfBuilding></PathOfBuilding>")

if __name__ == "__main__":
    unittest.main()
