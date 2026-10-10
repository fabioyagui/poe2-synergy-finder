import unittest
from src import trade

STATS={"result":[
    {"id":"explicit","label":"Explicit","entries":[
        {"id":"explicit.stat_life","text":"+# to maximum Life"},
        {"id":"explicit.stat_strength","text":"+# to Strength"},
        {"id":"explicit.stat_fire","text":"Adds # to # Fire Damage"},
    ]},
    {"id":"pseudo","label":"Pseudo","entries":[
        {"id":"pseudo.pseudo_total_life","text":"+# total to maximum Life"},
    ]},
]}

class TradeV19Tests(unittest.TestCase):
    def test_stat_pattern_keeps_sign_and_percent_shape(self):
        self.assertEqual(trade.stat_pattern('+123 to maximum Life'), '+# to maximum life')
        self.assertEqual(trade.stat_pattern('Adds 12 to 34 Fire Damage'), 'adds # to # fire damage')
        self.assertEqual(trade.stat_pattern('+28(27-32) to maximum Mana'), '+# to maximum mana')
        self.assertEqual(trade.numeric_values('-12% to Fire Resistance'),[-12])

    def test_matches_rendered_item_mods(self):
        rows=trade.match_item_mods(['+123 to maximum Life','Adds 12 to 34 Fire Damage','Not a trade stat'],STATS)
        self.assertTrue(rows[0]['matched'])
        self.assertEqual(rows[0]['id'],'explicit.stat_life')
        self.assertEqual(rows[0]['min'],123)
        self.assertEqual(rows[1]['values'],[12,34])
        self.assertIsNone(rows[1]['min'])
        self.assertFalse(rows[2]['matched'])


    def test_pob_roll_ranges_are_removed_for_matching_but_preserved_as_hint(self):
        stats={"result":[{"id":"explicit","label":"Explicit","entries":[
            {"id":"explicit.stat_es","text":"#% increased Energy Shield"},
            {"id":"explicit.stat_mana","text":"+# to maximum Mana"},
        ]}]}
        rows=trade.match_item_mods(['37(33-38)% increased Energy Shield','+28(27-32) to maximum Mana'],stats)
        self.assertEqual(rows[0]['text'],'37% increased Energy Shield')
        self.assertEqual(rows[0]['roll_ranges'],[{'min':33,'max':38}])
        self.assertEqual(rows[0]['min'],37)
        self.assertEqual(rows[1]['id'],'explicit.stat_mana')
        self.assertEqual(rows[1]['roll_ranges'],[{'min':27,'max':32}])

    def test_rare_query_uses_base_not_generated_name(self):
        item={'rarity':'Rare','name':'Solar Needle','base_type':'Rattling Sceptre'}
        q=trade.build_search_query(item,[{'id':'explicit.stat_strength','enabled':True,'min':20,'max':''}])
        self.assertEqual(q['query']['type'],'Rattling Sceptre')
        self.assertNotIn('name',q['query'])
        self.assertEqual(q['query']['stats'][0]['filters'][0]['value']['min'],20)

    def test_unique_query_keeps_exact_name(self):
        item={'rarity':'Unique','name':'The Burning Monolith','base_type':'Heavy Belt'}
        q=trade.build_search_query(item,[],base_only=True)
        self.assertEqual(q['query']['name'],'The Burning Monolith')
        self.assertEqual(q['query']['type'],'Heavy Belt')
        self.assertEqual(q['query']['stats'],[])

if __name__=='__main__':unittest.main()
