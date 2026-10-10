import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from src import workbench, tree_simulator as ts
from src.pob_engine import EngineError
from tests.tree_sim_fixtures import FixtureEngine, XML
HASH=hashlib.sha256(XML.encode()).hexdigest()

class WorkbenchEngine(FixtureEngine):
    def request(self,action,params=None,timeout=20):
        if action.startswith('sf_workbench_'):
            if self.fail:raise EngineError('Falha de teste')
            if action=='sf_workbench_visual':
                result=super().request('sf_tree_context')['result']
                for i,n in enumerate(result['nodes']):n.update(x=i*100,y=(i%4)*120,links=[3] if n['id']==2 else [])
                result.update(visual_protocol=1,bounds={'min_x':0,'min_y':0,'max_x':10000,'max_y':400},edges=[{'a':2,'b':3}])
                return {'result':result}
            groups=super().request('sf_tree_context')['result']['groups']
            if action=='sf_workbench_calcs':
                return {'result':{'protocol':1,'workbench_protocol':1,'groups':groups,'skill':{'group_index':1,'active_index':1,'name':'Fixture Skill'},
                   'output':{'Life':100,'Mana':0,'Duration':4.5,'FutureStat':19},'breakdowns':{'Life':['100 base']},'breakdown_keys':['Life'],
                   'modifier_sources':{'Life':[{'name':'Life','value':100,'source':'Tree:2'}],'Duration':{}},'supports':{},
                   'selection':{'actor':'player','buff_mode':'EFFECTIVE'}}}
            if action=='sf_workbench_suggest':
                p={'node_id':3,'mode':'path'}
                plan=super().request('sf_tree_plan',p)['result']
                return {'result':{'protocol':1,'workbench_protocol':1,'kind':'suggestions','control_differences':{},'rows':[
                   {'node_id':3,'plan':plan,'baseline':{'Life':100},'variant':{'Life':110},'before':100,'after':110}],
                   'errors':{},'eligible':20,'evaluated':12,'metric':'Life','point_budget_verified':False}}
        return super().request(action,params,timeout)

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.engine=WorkbenchEngine()
        self.patches=[mock.patch.object(ts,'ENGINE',self.engine),mock.patch.object(ts.pob_bridge,'load_current_xml',return_value=XML)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_geometry_comes_from_engine(self):
        d=workbench.visual_context();self.assertTrue(d['original_restored']);self.assertEqual(d['build_hash'],HASH);self.assertGreater(len(d['nodes']),10);self.assertEqual(d['nodes'][0]['x'],0)
    def test_read_restores_original(self):
        workbench.calcs({});self.assertGreaterEqual(len(self.engine.loaded),2);self.assertEqual(self.engine.loaded[-1][0],XML)
    def test_zero_value_retained(self):
        d=workbench.calcs({});self.assertEqual(next(r for r in d['metrics'] if r['key']=='Mana')['value'],0)
    def test_unknown_metric_retained(self):
        d=workbench.calcs({});self.assertEqual(next(r for r in d['metrics'] if r['key']=='FutureStat')['category'],'Outros outputs do PoB')
    def test_empty_lua_arrays_normalized(self):
        d=workbench.calcs({});self.assertEqual(d['supports'],[]);self.assertEqual(d['modifier_sources']['Duration'],[])
    def test_missing_not_filled_with_zero(self):
        d=workbench.calcs({});self.assertNotIn('IgniteDPS',d['output'])
    def test_stale_build_rejected(self):
        with self.assertRaises(EngineError):workbench.calcs({'build_hash':'f'*64})
    def test_stopped_engine_rejected(self):
        self.engine.running=False
        with self.assertRaises(EngineError):workbench.visual_context()
    def test_api_failure_does_not_modify_original(self):
        self.engine.fail=True
        with self.assertRaises(EngineError):workbench.calcs({})
        self.assertEqual(self.engine.loaded[-1][0],XML)
    def test_invalid_selection(self):
        for body in [{'group_index':True},{'group_index':-1},{'active_index':'2'},{'actor':'other'},{'buff_mode':'fake'},{'build_hash':'short'}]:
            with self.subTest(body=body),self.assertRaises(ValueError):workbench.selection(body)
    def test_suggestions_bounded(self):
        body={'build_hash':HASH,'fingerprint':'fixture:1,2,9'}
        for extra in [{'limit':17},{'max_points':6},{'metric':'NotAMetric'},{'query':'x'*101}]:
            with self.assertRaises(ValueError):workbench.suggestions({**body,**extra})
    def test_suggestions_report_scope(self):
        d=workbench.suggestions({'build_hash':HASH,'fingerprint':'fixture:1,2,9'});self.assertEqual(d['evaluated'],12);self.assertEqual(d['eligible'],20);self.assertTrue(d['original_restored']);self.assertFalse(d['point_budget_verified']);self.assertEqual(d['rows'][0]['metrics'][0]['delta'],10)
    def test_require_identity_for_suggestions(self):
        with self.assertRaises(ValueError):workbench.suggestions({})
    def test_nonfinite_output_excluded(self):
        rows=workbench.metric_catalog({'Life':float('nan'),'Mana':float('inf'),'Armour':0},{},{})
        self.assertEqual([r['key'] for r in rows],['Armour'])
    def test_breakdown_not_guessed(self):
        rows=workbench.metric_catalog({'TotalDPS':100},{'AverageDamage':['anything']},{})
        self.assertFalse(rows[0]['breakdown_available'])
    def test_extension_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'API').mkdir();(root/'API/Handlers.lua').write_text('local handlers={}\nrequire("API.SynergyTree").install(handlers)\nreturn {handlers=handlers}')
            workbench.install_extension(root);one=(root/'API/Handlers.lua').read_text();workbench.install_extension(root)
            self.assertEqual(one,(root/'API/Handlers.lua').read_text());self.assertTrue((root/'API/SynergyWorkbench.lua').exists())
    def test_extension_unrecognized_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'API').mkdir();target=root/'API/Handlers.lua';target.write_text('not recognized')
            with self.assertRaises(EngineError):workbench.install_extension(root)
            self.assertEqual(target.read_text(),'not recognized')

if __name__=='__main__':unittest.main()
