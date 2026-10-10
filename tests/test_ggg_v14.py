import json
from pathlib import Path
import unittest
from unittest import mock
from src import ggg_api

class GggApiTests(unittest.TestCase):
    def test_character_snapshot_conversion(self):
        char={
            "id":"a"*64,"name":"TestMerc","class":"Gemling Legionnaire","league":"Standard","level":93,"experience":123,
            "metadata":{"version":"0.4.0"},
            "equipment":[{"id":"b"*64,"name":"Rare Gun","typeLine":"Advanced Crossbow","rarity":"Rare","inventoryId":"Weapon","ilvl":80,"explicitMods":[{"description":"+10 to Dexterity"}]}],
            "skills":[{"id":"c"*64,"typeLine":"Oil Grenade","gemSkill":"Oil Grenade","properties":[{"name":"Level","values":[["20",0]]}],"socketedItems":[{"id":"d"*64,"typeLine":"Short Fuse II","support":True,"properties":[{"name":"Level","values":[["1",0]]}]}]}],
            "passives":{"hashes":[1,2,3],"specialisations":{"set1":[4,5]},"quest_stats":["+10 Spirit"]},
            "jewels":[]
        }
        s=ggg_api.character_to_summary(char)
        self.assertEqual(s["source_type"],"ggg-character")
        self.assertFalse(s["has_pob_xml"])
        self.assertEqual(s["character_name"],"TestMerc")
        self.assertEqual(s["skills"][0]["main_gem"],"Oil Grenade")
        self.assertEqual(s["skills"][0]["gems"][1]["name"],"Short Fuse II")
        self.assertEqual(s["items"]["slots"][0]["slot"],"Weapon")
        self.assertEqual(s["tree"]["allocated_nodes"],5)

    def test_pkce_url_uses_own_configured_client(self):
        with mock.patch.object(ggg_api,"load_config",return_value={"client_id":"my-synergy-client","contact":"me@example.com"}):
            d=ggg_api.start_oauth(8777)
        self.assertIn("client_id=my-synergy-client",d["authorize_url"])
        self.assertIn("code_challenge_method=S256",d["authorize_url"])
        self.assertIn("account%3Acharacters",d["authorize_url"])
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A8777%2Foauth%2Fcallback",d["authorize_url"])
        self.assertEqual(d["redirect_uri"],"http://127.0.0.1:8777/oauth/callback")

    def test_does_not_embed_pob_client_id(self):
        src=Path(ggg_api.__file__).read_text(encoding="utf-8")
        self.assertNotIn('client_id=pob',src)
        self.assertNotIn('"pob"',src)

    def test_snapshot_json_wrapper(self):
        payload={"character":{"name":"X","class":"Mercenary","level":1,"skills":[],"equipment":[],"passives":{"hashes":[]}}}
        d=ggg_api.import_snapshot_json(json.dumps(payload))
        self.assertEqual(d["summary"]["character_name"],"X")

if __name__=="__main__":unittest.main()
