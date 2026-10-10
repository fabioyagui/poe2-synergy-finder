"""Fixtures are never loaded in production. Real-node excerpts validate field shape,
not the complete live corpus. All other names/values are intentionally synthetic.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.fixtures import datasets,write_fixture
from src import storage
from src.importer import import_files,parse as parse_gems
from src.tree_importer import parse,import_tree,TREE_FILES,SOURCE,stable_id
from src.translations import Translator
from src.semantics import text_relations,enrich
from src.catalog import Catalog
from src.interactions import build
from src.updater import Jobs


def translations():
    return {TREE_FILES[2]:[
        {'ids':['base_ignite_effect_+%'],'English':[
            {'condition':[{'min':1}],'format':['#'],'index_handlers':[[]],
             'string':'{0}% increased [Ignite] Magnitude'},
            {'condition':[{'max':-1}],'format':['#'],'index_handlers':[['negate']],
             'string':'{0}% reduced [Ignite] Magnitude'}]},
        {'ids':['test_always_ignite'],'English':[
            {'condition':[{'min':1}],'format':['ignore'],'index_handlers':[[]],'string':'Your Hits always [Ignite]'}]},
        {'ids':['test_cannot_ignite'],'English':[
            {'condition':[{'min':1}],'format':['ignore'],'index_handlers':[[]],'string':'Your Hits cannot [Ignite]'}]},
    ]}

def node(name,stats,**more):
    return {'name':name,'stats':stats,'hash':more.pop('hash',999),'is_notable':False,
            'is_keystone':False,'is_icon_only':False,**more}

def tree_datasets():
    tree={'name':'Default [TEST]','groups':{},'passive_nodes':{
        '101':node('Ignite modifier [TEST]',{'base_ignite_effect_+%':25},hash=101,is_notable=True,out=[102]),
        '102':node('Independent rule [TEST]',{'unknown_test_stat':9},hash=102),
        '103':node('Ignite enabler [TEST]',{'test_always_ignite':1},hash=103,ascendancy='TestWitch1'),
        '104':node('Ignite prevention [TEST]',{'test_cannot_ignite':1},hash=104,is_keystone=True),
        '105':node('Other ascendancy [TEST]',{'base_ignite_effect_+%':50},hash=105,ascendancy='TestWitch2'),
        '106':node('Decorative [TEST]',{},hash=106,is_icon_only=True),
        '107':node('Granted skill [TEST]',{},hash=107,ascendancy='TestWitch1',granted_skill='test/flame'),
    }}
    asc={'TestWitch1':{'name':'Ascendancy One [TEST]','character':['Metadata/test','TestWitch']},
         'TestWitch2':{'name':'Ascendancy Two [TEST]','character':['Metadata/test','TestWitch']}}
    return tree,asc,translations()

def write_tree(folder):
    folder=Path(folder);tree,asc,tr=tree_datasets()
    for name,value in {TREE_FILES[0]:tree,TREE_FILES[1]:asc,**tr}.items():
        p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value),encoding='utf-8')
    return folder

class TranslationTests(unittest.TestCase):
    def test_positive(self):
        rows,missing=Translator(translations()).render({'base_ignite_effect_+%':15})
        self.assertEqual(rows[0]['text'],'15% increased [Ignite] Magnitude');self.assertEqual(missing,[])
    def test_negative_handler(self):
        rows,_=Translator(translations()).render({'base_ignite_effect_+%':-12});self.assertIn('12% reduced',rows[0]['text'])
    def test_unknown_handler_not_guessed(self):
        data=translations();data[TREE_FILES[2]][0]['English'][0]['index_handlers']=[['unimplemented']]
        rows,missing=Translator(data).render({'base_ignite_effect_+%':15});self.assertFalse(rows);self.assertEqual(len(missing),1)
    def test_unknown_stat_kept(self):self.assertEqual(Translator(translations()).render({'not_known':10})[1],['not_known'])
    def test_zero_has_no_effect(self):self.assertFalse(Translator(translations()).render({'test_always_ignite':0})[0])
    def test_missing_multi_stat_not_zero(self):
        d=translations();d[TREE_FILES[2]][0]['ids']=['base_ignite_effect_+%','missing']
        self.assertFalse(Translator(d).render({'base_ignite_effect_+%':12})[0])
    def test_unresolved_placeholder(self):
        d=translations();d[TREE_FILES[2]][0]['English'][0]['string']='{9} test'
        self.assertFalse(Translator(d).render({'base_ignite_effect_+%':12})[0])

class SemanticTests(unittest.TestCase):
    def effects(self,text):return [l for l in text_relations(text,'test.path') if l['relation']!='MENTIONS']
    def test_fire_not_ignite(self):self.assertFalse(any(l['concept']=='IGNITE' for l in self.effects('Deals Fire Damage.')))
    def test_mention_not_producer(self):self.assertEqual(self.effects('An unusual interaction with Ignite.'),[])
    def test_always_is_producer(self):self.assertEqual(self.effects('Your Hits always Ignite')[0]['relation'],'PRODUCES')
    def test_conditional_application(self):
        l=self.effects('Your Hits always Ignite while on Low Life')[0];self.assertTrue(l['condition']);self.assertEqual(l['relation'],'PRODUCES')
    def test_chance_is_not_uptime(self):
        l=self.effects('25% chance to Ignite')[0];self.assertEqual(l['relation'],'ENABLES');self.assertTrue(l['condition'])
    def test_cannot_inflict_list(self):
        ls=self.effects('Supported Skills cannot inflict Freeze, Shock or Ignite.')
        self.assertEqual({l['concept'] for l in ls if l['relation']=='PREVENTS'},{'FREEZE','SHOCK','IGNITE'})
    def test_no_prevents_on_self_immunity(self):
        ls=self.effects('You cannot be Ignited.');self.assertFalse(any(l['relation']=='PREVENTS' and l['concept']=='IGNITE' for l in ls))
    def test_ailment_on_self_scoped(self):
        ls=self.effects('20% reduced duration of Ignites on you.');self.assertTrue(any(l['concept']=='SELFIGNITE' for l in ls))
    def test_consume(self):self.assertEqual(self.effects('Consumes Ignite on Hit.')[0]['relation'],'CONSUMES')
    def test_increased_is_not_produce(self):
        ls=self.effects('20% increased Ignite Magnitude.');self.assertEqual(ls[0]['relation'],'AMPLIFIES');self.assertEqual(ls[0]['aspect'],'magnitude')
    def test_benefit_against_is_requirement(self):
        ls=self.effects('20% more Fire Damage against Ignited enemies.');self.assertTrue(any(l['relation']=='REQUIRES' and l['concept']=='IGNITE' for l in ls))
    def test_more_chance_not_enabler(self):
        ls=self.effects('25% increased chance to Ignite.');self.assertFalse(any(l['relation']=='ENABLES' for l in ls))
    def test_intro_supports_is_not_producer(self):self.assertEqual(self.effects('Supports Skills that always Ignite.'),[])
    def test_minion_scope(self):self.assertEqual(self.effects('Minions always Ignite.')[0]['scope'],'minion')
    def test_generate_condition(self):
        ls=self.effects('Gain a Power Charge on Kill.');self.assertEqual(ls[0]['relation'],'GENERATES');self.assertTrue(ls[0]['condition'])
    def test_no_consume_gained_resource(self):
        ls=self.effects('Consume a Power Charge to gain a Frenzy Charge.')
        self.assertFalse(any(l['relation']=='CONSUMES' and l['concept']=='FRENZYCHARGE' for l in ls))
    def test_negative_stat(self):
        e={'kind':'PASSIVE','stats':[{'id':'base_ignite_effect_+%','value':-8,'path':'stats.x','semantic_fixed':True}],'texts':[],'links':[]}
        self.assertEqual(enrich(e)['links'][0]['relation'],'REDUCES')

class TreeTests(unittest.TestCase):
    def setUp(self):self.data=tree_datasets();self.rows,self.diag,self.edges,self.nodes=parse(*self.data);self.es={e['source_id']:e for e,_ in self.rows}
    def test_complete_corpus(self):self.assertEqual(len(self.rows),9)
    def test_nested_container(self):
        t,a,x=self.data;rows,_,_,_=parse({'wrapper':t},a,x);self.assertEqual(len(rows),9)
    def test_wrong_file_fails(self):
        with self.assertRaises(ValueError):parse({'unknown':'invalid'},self.data[1],{})
    def test_asc_metadata_separate(self):self.assertEqual(self.es['ascendancy:TestWitch1']['kind'],'ASCENDANCY')
    def test_asc_node_classified(self):self.assertEqual(self.es['node:103']['kind'],'ASCENDANCY_NODE')
    def test_notable(self):self.assertEqual(self.es['node:101']['kind'],'NOTABLE')
    def test_keystone(self):self.assertEqual(self.es['node:104']['kind'],'KEYSTONE')
    def test_decorative_retained_not_recommended(self):self.assertFalse(self.es['node:106']['selectable'])
    def test_unknown_stats(self):self.assertEqual(self.es['node:102']['untranslated_stats'],['unknown_test_stat'])
    def test_source_paths(self):self.assertTrue(self.es['node:101']['texts'][0]['path'].startswith('tree.passive_nodes.101.stats.'))
    def test_grants_skill(self):self.assertEqual(self.es['node:107']['granted_gem_id'],'test/flame')
    def test_no_attribute_guess(self):self.assertEqual(self.es['node:101']['color'],'w')
    def test_edges_explicit(self):self.assertEqual(len(self.edges),1)
    def test_different_names_same_ids_stable(self):
        data=copy.deepcopy(self.data);data[0]['passive_nodes']['101']['name']='new name';rs,_,_,_=parse(*data)
        self.assertEqual(next(e['id'] for e,_ in rs if e['source_id']=='node:101'),self.es['node:101']['id'])
    def test_observed_repoe_node_shapes(self):
        # These three node records are excerpts observed in Default.min.json on
        # 2026-09-12. Other file portions and values remain synthetic test context.
        real={
            '34290':{'hash':34290,'id':'ignite14','name':'Ignite Magnitude','is_notable':False,'is_keystone':False,'stats':{'base_ignite_effect_+%':10}},
            '34419':{'hash':34419,'id':'AscendancyWitch1Notable9','name':'Grinning Immolation','ascendancy':'Witch1','is_notable':True,'is_keystone':False,'stats':{'infernalist_burn_life_and_es_%_per_second_if_crit_recently':15,'infernalist_critical_strike_multiplier_+%_final':50}},
            '34478':{'hash':34478,'id':'companions53','name':'Bond of the Viper','is_notable':True,'is_keystone':False,'stats':{'companion_chance_to_poison_on_hit_%':40,'skill_effect_duration_+%':16}},
        }
        rows,d,_,_=parse({'skills':real},{'Witch1':{'name':'Infernalist'}},{})
        self.assertEqual(len(rows),4);self.assertEqual(d['nodes'],3)
        e=next(e for e,_ in rows if e['name']=='Ignite Magnitude');self.assertTrue(any(l['relation']=='AMPLIFIES' and l['concept']=='IGNITE' for l in e['links']))
        e=next(e for e,_ in rows if e['name']=='Grinning Immolation');self.assertEqual(e['ascendancy'],'Infernalist')

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch.object(storage,'DATA',self.root/'data'),patch.object(storage,'DB',self.root/'data/db.sqlite3')]
        for p in self.patches:p.start()
        storage.init();self.folder=write_fixture(self.root/'raw');write_tree(self.folder)
        import_files(self.folder);import_tree(self.folder)
        self.cat=Catalog();self.flame=next(e for e in self.cat.ordered if e['source_id']=='test/flame')
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_all_categories(self):self.assertEqual(self.cat.status()['entities'],19)
    def test_only_skills_in_anchor(self):self.assertEqual(self.cat.skills()['total'],3)
    def test_only_passives(self):self.assertEqual(self.cat.explore(scope='passives')['total'],3)
    def test_only_asc(self):self.assertEqual(self.cat.explore(scope='ascendancies')['total'],5)
    def test_include_decoration(self):self.assertEqual(self.cat.explore(scope='all',include_decorative=True)['total'],19)
    def test_versions(self):self.assertEqual(self.cat.status()['tree_import']['repoe_version'],'TEST - synthetic fixture')
    def test_tree_raw(self):
        e=next(e for e in self.cat.ordered if e['source_id']=='node:101');self.assertEqual(self.cat.get(e['id'],True)['raw']['tree_nodes']['hash'],101)
    def test_reimport_gems_keeps_tree(self):import_files(self.folder);self.assertEqual(Catalog().status()['entities'],19)
    def test_reimport_tree_keeps_gems(self):import_tree(self.folder);self.assertEqual(Catalog().status()['entities'],19)
    def test_invalid_tree_preserves_old(self):
        (self.folder/TREE_FILES[0]).write_text('{}')
        with self.assertRaises(ValueError):import_tree(self.folder)
        self.assertEqual(Catalog().status()['entities'],19)
    def test_atomic_full_job_failure(self):
        old=Catalog().status()['links']
        gpath=self.folder/'skill_gems.min.json';gs=json.loads(gpath.read_text());gs['test/red']['support_text']='Different';gpath.write_text(json.dumps(gs))
        (self.folder/TREE_FILES[0]).write_text('{}')
        job=Jobs();job.start('local',str(self.folder));job.thread.join(10)
        self.assertIsNotNone(job.snapshot()['error']);self.assertEqual(Catalog().status()['links'],old)
    def test_topics(self):self.assertTrue(build(self.cat)['topics'])
    def test_cross_category_chain(self):
        data=build(self.cat,'Ignite',self.flame['id']);self.assertTrue(data['paths'])
        self.assertTrue(any(p['a']['kind']=='ASCENDANCY_NODE' and p['b']['kind']=='NOTABLE' for p in data['paths']))
    def test_exclusive_ascendancies_not_paired(self):
        data=build(self.cat,'Ignite');self.assertFalse(any(p['a']['ascendancy_id'] and p['b']['ascendancy_id'] and p['a']['ascendancy_id']!=p['b']['ascendancy_id'] for p in data['paths']))
    def test_prevention_visible(self):
        data=build(self.cat,'Ignite');g=next(g for g in data['groups'] if g['key']=='prevents');self.assertTrue(g['results'])
    def test_no_score(self):self.assertNotIn('score',json.dumps(build(self.cat,'Ignite')))
    def test_case_agnostic(self):self.assertEqual(build(self.cat,'ignite')['entity_count'],build(self.cat,'IGNITE')['entity_count'])
    def test_patch_mismatch_warns(self):
        import_tree(self.folder,version='DIFFERENT');data=build(Catalog(),'Ignite');self.assertTrue(data['source_warnings'])
    def test_granted_skill_link(self):
        e=next(e for e in self.cat.ordered if e['source_id']=='node:107');self.assertEqual(self.cat.get(e['id'])['granted_gem']['id'],self.flame['id'])
    def test_unknown_tree_stat_searchable(self):self.assertEqual(self.cat.explore(q='unknown_test_stat',scope='all')['total'],1)
    def test_gem_tags_survive_tree_import(self):self.assertEqual(self.flame['tags'],datasets()[0]['test/flame']['tags'])

if __name__=='__main__':unittest.main()

class DownloadWorkflowTests(unittest.TestCase):
    # Mocked transport, not live internet access. Reuse isolated setup only.
    setUp=IntegrationTests.setUp
    tearDown=IntegrationTests.tearDown
    def test_snapshot_download_seven_files(self):
        import io
        from src.updater import BASE,FILES
        from tests.fixtures import datasets
        t,a,tr=tree_datasets();g,s,types=datasets()
        data=dict(zip(FILES[:3],[g,s,types]));data.update({TREE_FILES[0]:t,TREE_FILES[1]:a,**tr,TREE_FILES[3]:[]})
        # Empty translation catalog is legal: it has no extra translations.
        data[TREE_FILES[3]]=tr[TREE_FILES[2]]
        class Response(io.BytesIO):
            def __init__(self,b):super().__init__(b);self.headers={'Content-Length':str(len(b))}
        def fake_open(request,timeout):
            name=request.full_url.removeprefix(BASE)
            body=json.dumps(data[name]).encode() if name else b'<h1>RePoE - PoE2 version TEST-1</h1>'
            return Response(body)
        job=Jobs()
        with patch('src.updater.urlopen',side_effect=fake_open):
            job.start('online');job.thread.join(10)
        result=job.snapshot();self.assertFalse(result['running']);self.assertIsNone(result['error'])
        self.assertEqual(Catalog().meta['repoe_version'],'TEST-1')
        self.assertEqual(Catalog().tree_meta['repoe_version'],'TEST-1')
        self.assertEqual(len(Catalog().tree_meta['hashes']),4)
    def test_download_failure_preserves_existing_tree_and_gems(self):
        job=Jobs()
        with patch('src.updater.urlopen',side_effect=OSError('fixture network failure')):
            job.start('online');job.thread.join(10)
        self.assertTrue(job.snapshot()['error']);self.assertEqual(Catalog().status()['entities'],19)
    def test_cancel_before_commit(self):
        job=Jobs();job.stop_event.set()
        with self.assertRaises(Exception):job.check_cancelled()
        self.assertEqual(Catalog().status()['entities'],19)
    def test_duplicate_job_rejected(self):
        job=Jobs();job.state['running']=True
        with self.assertRaises(RuntimeError):job.start('online')
