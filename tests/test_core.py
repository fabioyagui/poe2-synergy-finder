import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.fixtures import datasets,write_fixture
from src import storage
from src.importer import parse,attribute,concept,plain,import_files
from src.catalog import Catalog,compatibility,explain_expression
from src.compatibility import evaluate

class ParserTests(unittest.TestCase):
    def setUp(self):
        self.data=datasets();entries,self.diag=parse(*self.data)
        self.entries={e['source_id']:e for e,b in entries}
    def test_every_record(self):self.assertEqual(len(self.entries),len(self.data[0]))
    def test_no_curated_name_list(self):
        g,s,t=self.data;g['test/flame']['base_item']['display_name']='Entirely new arbitrary skill';e,d=parse(g,s,t)
        self.assertTrue(any(x['name']=='Entirely new arbitrary skill' for x,b in e))
    def test_all_tags_retained(self):self.assertEqual(self.entries['test/flame']['tags'],self.data[0]['test/flame']['tags'])
    def test_colors_direct(self):
        for name,color in [('red','r'),('green','g'),('blue','b')]:self.assertEqual(self.entries['test/'+name]['color'],color)
    def test_color_not_damage(self):self.assertEqual(self.entries['test/red']['attribute'],'STR')
    def test_color_priority(self):self.assertEqual(attribute({'color':'g','requirement_weights':{'strength':100}})['attribute'],'DEX')
    def test_color_fallback(self):self.assertEqual(attribute({'requirement_weights':{'intelligence':100}})['color'],'b')
    def test_ambiguous_color(self):self.assertEqual(attribute({'requirement_weights':{'intelligence':100,'strength':100}})['color'],'w')
    def test_color_unknown(self):self.assertEqual(attribute({'tags':['fire']})['color'],'w')
    def test_internal_alias_resolution(self):self.assertEqual(self.diag['unresolved'],0)
    def test_effects_separate(self):
        e=self.entries['test/multi'];self.assertEqual(len(e['components']),2)
        self.assertNotIn('DamageOverTime',e['components'][0]['types'])
    def test_nested_type_path(self):
        links=self.entries['test/flame']['links'];self.assertTrue(any(l['path']=='skills.outer-flame.active_skill.types[0]' for l in links))
    def test_postfix_preserved(self):self.assertEqual(self.entries['test/dot']['rules']['allowed_types'],['Spell','DamageOverTime','AND'])
    def test_no_operator_as_link(self):self.assertFalse(any(l['concept'] in {'AND','OR','NOT'} for e in self.entries.values() for l in e['links']))
    def test_consume_type(self):self.assertTrue(any(l['relation']=='CONSUMES' and l['concept']=='IGNITE' for l in self.entries['test/red']['links']))
    def test_consume_path(self):self.assertTrue(any(l['path']=='skills.outer-red.support_gem.added_types[0]' for l in self.entries['test/red']['links']))
    def test_minion_scope_not_support(self):
        links=self.entries['test/minion']['links'];cs=[l for l in links if l['relation']=='CONSUMES'];self.assertTrue(cs);self.assertEqual(cs[0]['component'],'minion_of_supported_skill')
    def test_cannot_consume(self):
        self.assertTrue(any(l['relation']=='PREVENTS_CONSUMPTION' for l in self.entries['test/no']['links']))
        self.assertFalse(any(l['relation']=='CONSUMES' for l in self.entries['test/no']['links']))
    def test_no_fire_to_ignite_inference(self):self.assertFalse(any(l['concept']=='IGNITE' and l['relation']=='GENERATES' for l in self.entries['test/flame']['links']))
    def test_raw_stats_preserved(self):self.assertTrue(any(s['id']=='test_ignite_magnitude' and s['value']==30 for s in self.entries['test/blue']['stats']))
    def test_markup_plain(self):self.assertEqual(plain('[Consume|Consumes] [Ignite]'),'Consumes Ignite')
    def test_missing_rules_not_empty(self):self.assertIsNone(self.entries['test/missing']['rules']['allowed_types'])
    def test_legacy_retained(self):
        d=copy.deepcopy(self.data);d[0]['test/red']['base_item']['release_state']='legacy';e,_=parse(*d)
        self.assertTrue(any(x['source_id']=='test/red' and x['availability']=='legacy' for x,b in e))
    def test_duplicate_name_no_overwrite(self):
        d=copy.deepcopy(self.data);d[0]['test/red2']=copy.deepcopy(d[0]['test/red']);e,_=parse(*d)
        self.assertEqual(sum(x['name']=='Red consumer [TEST]' for x,b in e),2)
    def test_drain_rejected_primary(self):self.assertEqual(compatibility(self.entries['test/flame'],self.entries['test/dot'])['status'],'incompatible')
    def test_drain_not_from_secondary(self):self.assertEqual(compatibility(self.entries['test/multi'],self.entries['test/dot'])['status'],'incompatible')
    def test_choose_secondary(self):self.assertEqual(compatibility(self.entries['test/multi'],self.entries['test/dot'],'TestChild')['status'],'type_match')
    def test_rule_unknown(self):self.assertEqual(compatibility(self.entries['test/flame'],self.entries['test/missing'])['status'],'unknown')
    def test_rpn_residual_or(self):self.assertTrue(evaluate(['Attack','Spell','Fire','AND'],{'ATTACK'}))
    def test_rpn_not(self):self.assertTrue(evaluate(['Attack','NOT'],{'SPELL'}))
    def test_rpn_malformed(self):self.assertIsNone(evaluate(['AND'],{'SPELL'}))
    def test_expression_readable(self):self.assertEqual(explain_expression(['Spell','DamageOverTime','AND']),'(Spell E DamageOverTime)')
    def test_unresolved_not_approved(self):
        d=copy.deepcopy(self.data);d[0]['test/flame']['grants_skills']=['NOT_FOUND'];e,diag=parse(*d)
        es={x['source_id']:x for x,b in e};self.assertEqual(diag['unresolved'],1)
        self.assertEqual(compatibility(es['test/flame'],es['test/blue'])['status'],'unknown')
    def test_all_1300_gems(self):
        g,s,t=datasets();source=g['test/blue'];g={f'generated/{i}':dict(source) for i in range(1300)}
        e,d=parse(g,s,t);self.assertEqual(len(e),1300)

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.p1=patch.object(storage,'DATA',self.root/'data');self.p2=patch.object(storage,'DB',self.root/'data'/'database'/'test.db')
        self.p1.start();self.p2.start();storage.init();self.folder=write_fixture(self.root/'raw')
        import_files(self.folder);self.cat=Catalog()
        self.flame=next(e for e in self.cat.ordered if e['source_id']=='test/flame')
    def tearDown(self):self.p2.stop();self.p1.stop();self.temp.cleanup()
    def test_no_seed_base(self):self.assertEqual(self.cat.status()['entities'],10)
    def test_all_supports(self):self.assertEqual(self.cat.explore()['total'],7)
    def test_search_returns_all_tags(self):
        r=self.cat.explore(q='ignite')['results'];e=next(x for x in r if x['source_id']=='test/blue')
        self.assertEqual(e['tags'],['support','fire','duration'])
    def test_stat_search(self):self.assertTrue(any(e['source_id']=='test/blue' for e in self.cat.explore(q='test_ignite_magnitude')['results']))
    def test_filter_attribute(self):self.assertEqual(self.cat.explore(color='r')['total'],1)
    def test_filter_tag(self):self.assertEqual(self.cat.explore(tag='fire')['total'],2)
    def test_filter_real_consume(self):self.assertEqual(self.cat.explore(q='Ignite',relation='consumes')['total'],2)
    def test_filter_compatibility(self):
        rows=self.cat.explore(skill_id=self.flame['id'])['results'];ids=[r['source_id'] for r in rows]
        self.assertNotIn('test/dot',ids);self.assertNotIn('test/green',ids);self.assertNotIn('test/missing',ids)
    def test_global_skills(self):self.assertEqual(self.cat.explore(scope='all')['total'],10)
    def test_no_score(self):self.assertFalse(any('score' in e for e in self.cat.explore()['results']))
    def test_raw_retrievable(self):self.assertEqual(self.cat.get(self.flame['id'],True)['raw']['gem'],datasets()[0]['test/flame'])
    def test_source_version(self):self.assertEqual(self.cat.meta['repoe_version'],'TEST - synthetic fixture')
    def test_hashes(self):self.assertEqual(len(self.cat.meta['hashes']),3)
    def test_atomic_error(self):
        old=self.cat.status()['entities'];(self.folder/'skills.min.json').write_text('{}')
        with self.assertRaises(ValueError):import_files(self.folder)
        self.assertEqual(Catalog().status()['entities'],old)
    def test_no_profile_table(self):
        with storage.connect() as c:self.assertFalse(c.execute("SELECT name FROM sqlite_master WHERE name='profiles'").fetchone())
    def test_reimport_idempotent(self):
        before=self.cat.status();import_files(self.folder);after=Catalog().status();self.assertEqual(before['entities'],after['entities']);self.assertEqual(before['links'],after['links'])
    def test_paginated(self):self.assertEqual(len(self.cat.explore(offset=1,limit=2)['results']),2)
    def test_explain_unknown(self):
        r=self.cat.explore(skill_id=self.flame['id'],mode='unknown')['results'];self.assertEqual(len(r),1);self.assertEqual(r[0]['source_id'],'test/missing')

if __name__=='__main__':unittest.main()
