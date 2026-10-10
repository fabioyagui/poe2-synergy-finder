import copy
import hashlib
import threading
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from src import tree_simulator as ts
from src.pob_engine import EngineError

XML='<PathOfBuilding2><Tree><Spec nodes="1,2"/></Tree></PathOfBuilding2>'
HASH=hashlib.sha256(XML.encode()).hexdigest()
NODE={'id':3,'name':'Fixture life point','kind':'Normal','stats':['10 to maximum Life'],'editable':True,'allocated':False}
PLAN={'protocol':1,'target':NODE,'changes':[NODE],'add_ids':[3],'remove_ids':{},'required_ids':[3],
      'fingerprint':'fixture','action':'add','mode':'path','total_delta':1,'ordinary_delta':1,'ascendancy_delta':0}
BODY={'node_id':3,'mode':'path','build_hash':HASH,'fingerprint':'fixture','group_index':1,'active_index':1}

class FakeEngine:
    def __init__(self):
        self.lock=threading.RLock();self.loaded=[];self.running=True;self.fail=False;self.fail_restore=False;self.response=None
    def is_running(self):return self.running
    def stop(self,force=False):self.running=False
    def load_xml(self,xml,name):
        self.loaded.append((xml,name))
        if self.fail_restore and len(self.loaded)>1:raise EngineError('restore failure')
    def request(self,action,params=None,timeout=20):
        if action=='sf_tree_state':return {'result':{'protocol':1,'fingerprint':'fixture','tree_version':'fixture'}}
        if self.fail:raise EngineError('synthetic failure')
        if self.response is not None:return {'result':copy.deepcopy(self.response)}
        if action=='sf_tree_context':return {'result':{'protocol':1,'nodes':[NODE],'groups':[{'effects':{}}]}}
        if action=='sf_tree_plan':return {'result':copy.deepcopy(PLAN)}
        return {'result':{'protocol':1,'baseline':{'Life':100,'Mana':40},'variant':{'Life':110,'Mana':40},
            'plan':copy.deepcopy(PLAN),'control_differences':{},'allocation_unchanged':True,
            'skill':{'name':'Fixture'},'tree_version':'fixture'}}

class TreeTransactions(TestCase):
    def setUp(self):
        self.engine=FakeEngine()
        self.patch1=mock.patch.object(ts,'ENGINE',self.engine)
        self.patch2=mock.patch.object(ts.pob_bridge,'load_current_xml',return_value=XML)
        self.patch1.start();self.patch2.start()
        self.addCleanup(self.patch1.stop);self.addCleanup(self.patch2.stop)
    def test_complete_compare_and_restore(self):
        r=ts.compare(BODY)
        self.assertTrue(r['original_restored']);self.assertTrue(r['numeric_check_passed'])
        self.assertEqual(len(self.engine.loaded),2);self.assertTrue(all(x[0]==XML for x in self.engine.loaded))
        self.assertEqual(next(x for x in r['metrics'] if x['key']=='Life')['delta'],10)
        self.assertFalse(r['point_budget_verified'])
    def test_failed_compare_still_restores(self):
        self.engine.fail=True
        with self.assertRaisesRegex(EngineError,'synthetic failure'):ts.compare(BODY)
        self.assertEqual(len(self.engine.loaded),2)
    def test_failed_restore_stops_engine_and_rejects_result(self):
        self.engine.fail_restore=True
        with self.assertRaisesRegex(EngineError,'motor parado'):ts.compare(BODY)
        self.assertFalse(self.engine.running)
    def test_context_normalizes_empty_arrays(self):
        r=ts.context();self.assertEqual(r['groups'][0]['effects'],[]);self.assertTrue(r['original_restored'])
    def test_preview_restores_and_normalizes(self):
        r=ts.preview(BODY);self.assertEqual(r['remove_ids'],[]);self.assertTrue(r['original_restored'])
    def test_stale_build_rejected_before_engine_mutation(self):
        with self.assertRaisesRegex(EngineError,'build mudou'):ts.compare({**BODY,'build_hash':'f'*64})
        self.assertEqual(self.engine.loaded,[])
    def test_no_engine_does_not_attempt_load(self):
        self.engine.running=False
        with self.assertRaisesRegex(EngineError,'Inicie o Motor'):ts.context()
        self.assertFalse(self.engine.loaded)
    def test_protocol_mismatch_explained(self):
        self.engine.response={'protocol':0}
        with self.assertRaisesRegex(EngineError,'módulo de árvore'):ts.context()
    def test_scalar_control_mismatch_is_not_approved(self):
        self.engine.response={'protocol':1,'plan':PLAN,'baseline':{'Life':100},'variant':{'Life':110},'control_differences':['Life']}
        r=ts.compare(BODY);self.assertFalse(r['numeric_check_passed'])
    def test_empty_outputs_not_success(self):
        self.engine.response={'protocol':1,'plan':PLAN,'baseline':{},'variant':{},'control_differences':{}}
        with self.assertRaisesRegex(EngineError,'retornou valores'):ts.compare(BODY)
    def test_concurrent_operations_hold_whole_lock(self):
        trace=[]
        original=self.engine.load_xml
        def record(xml,name):trace.append(threading.current_thread().name);original(xml,name)
        self.engine.load_xml=record
        jobs=[threading.Thread(target=lambda:ts.compare(BODY),name=f'T{i}') for i in range(3)]
        for j in jobs:j.start()
        for j in jobs:j.join()
        self.assertEqual(len(trace),6)
        for i in range(0,6,2):self.assertEqual(trace[i],trace[i+1])

class Metrics(TestCase):
    def test_missing_is_not_zero(self):
        r=ts.metric_rows({'Life':100},{})[0]
        self.assertIsNone(r['delta']);self.assertIsNone(r['pct']);self.assertIsNone(r['after'])
    def test_zero_baseline_no_percent(self):
        r=ts.metric_rows({'Life':0},{'Life':100})[0];self.assertIsNone(r['pct']);self.assertEqual(r['delta'],100)
    def test_boolean_not_numeric_improvement(self):
        r=ts.metric_rows({'Flag':False},{'Flag':True})[0];self.assertFalse(r['comparable']);self.assertIsNone(r['delta'])
    def test_future_metric_preserved(self):
        r=ts.metric_rows({'Future':10},{'Future':11})[0];self.assertEqual(r['pct'],10)
    def test_small_numeric_noise_ignored(self):
        self.assertFalse(ts.metric_rows({'Life':100},{'Life':100.000000001})[0]['changed'])
    def test_nan_not_exported_as_number(self):
        r=ts.metric_rows({'Life':100},{'Life':float('nan')})[0];self.assertFalse(r['comparable'])
    def test_payload_validation(self):
        for key,value in [('node_id',True),('node_id',3.0),('mode','invalid'),('group_index',-1),('build_hash','none')]:
            with self.subTest(key=key),self.assertRaises(ValueError):ts.validate_params({**BODY,key:value},True)

class Extension(TestCase):
    def test_extension_installs_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'API').mkdir();h=p/'API/Handlers.lua';h.write_text('local handlers = {}\nreturn handlers\n')
            ts.install_extension(p);first=h.read_text();ts.install_extension(p)
            self.assertEqual(first,h.read_text());self.assertTrue((p/'API/SynergyTree.lua').exists())
    def test_unknown_bridge_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'API').mkdir();h=p/'API/Handlers.lua';h.write_text('unknown')
            with self.assertRaises(EngineError):ts.install_extension(p)
            self.assertEqual(h.read_text(),'unknown')
