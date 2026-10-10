"""Synthetic data for HTTP and browser tests; not a PoB calculation."""
import copy
import threading
from src.pob_engine import EngineError

XML='<PathOfBuilding2><Build level="50" className="Mercenary" ascendClassName="Test"/><Tree activeSpec="1"><Spec id="1" nodes="1,2,9"/></Tree></PathOfBuilding2>'
SUMMARY={'level':50,'class_name':'Mercenary','ascendancy':'Test fixture','skills':[], 'tree':{'allocated_nodes':3},'items':{},'player_stats':{},'main_skill':'Fixture Skill','source':'Local test fixture','has_pob_xml':True}

def node(i,name,allocated=False,distance=1,stats=None,editable=True):
    return {'id':i,'name':name,'kind':'Normal','allocated':allocated,'allocation_mode':0,'path_distance':distance,
            'stats':stats or ['10 to maximum Life'],'editable':editable,'blocked_reason':None if editable else 'Ponto especial não suportado.'}
NODES=[node(2,'Life allocated',True),node(3,'Life nearby'),node(4,'Area distant',False,2,['8% increased Area of Effect']),
       node(8,'Special socket',False,1,editable=False),node(9,'Mana dependent',True),
       node(10,'<script>bad()</script>',False,3)]
NODES += [node(i,f'Fixture node {i}',False,4) for i in range(20,100)]

class FixtureEngine:
    def __init__(self):
        self.lock=threading.RLock();self.running=True;self.fail=False;self.loaded=[]
    def is_running(self):return self.running
    def stop(self,force=False):self.running=False
    def load_xml(self,xml,name):self.loaded.append((xml,name))
    def status(self):return {'running':self.running,'ready':True,'setup':{'ready':True,'checks':{},'config':{}}}
    def request(self,action,params=None,timeout=20):
        p=params or {}
        if action=='sf_tree_state':return {'result':{'protocol':1,'fingerprint':'fixture:1,2,9','tree_version':'fixture'}}
        if self.fail:raise EngineError('Falha simulada para teste')
        if action=='sf_tree_context':
            return {'result':{'protocol':1,'fingerprint':'fixture:1,2,9','tree_version':'fixture',
                'nodes':copy.deepcopy(NODES),'counts':{'known':True,'ordinary':2,'ascendancy':0},
                'active_weapon_set':1,'selected_group':1,
                'groups':[{'index':1,'enabled':True,'label':'Fixture Skill','active_index':1,'effects':[{'index':1,'name':'Fixture Skill','id':'fixture'}]}]}}
        n=next((copy.deepcopy(n) for n in NODES if n['id']==p.get('node_id')),None)
        if not n or not n['editable']:raise EngineError('Ponto não permitido')
        mode=p.get('mode','path');add=not n['allocated']
        ids=[n['id']]
        if mode=='path' and n['id']==4:ids=[3,4]
        if mode=='path' and n['id']==2:ids=[2,9]
        changes=[copy.deepcopy(next(n for n in NODES if n['id']==i)) for i in ids]
        plan={'protocol':1,'target':n,'changes':changes,'fingerprint':'fixture:1,2,9','add_ids':ids if add else [],
            'remove_ids':[] if add else ids,'required_ids':ids,'action':'add' if add else 'remove','mode':mode,
            'ordinary_delta':len(ids)*(1 if add else -1),'ascendancy_delta':0,'total_delta':len(ids)*(1 if add else -1),
            'isolated_hypothesis':mode=='isolated' and n['id'] in [2,4], 'point_budget_verified':False}
        if action=='sf_tree_plan':return {'result':plan}
        if action=='sf_tree_compare':
            return {'result':{'protocol':1,'plan':plan,'baseline':{'Life':100,'Mana':40,'FutureMetric':True},
                'variant':{'Life':100+10*plan['total_delta'],'Mana':40,'FutureMetric':True},
                'control_differences':[],'allocation_unchanged':True,'calculator':'SYNTHETIC TEST - not PoB',
                'skill':{'name':'Fixture Skill'},'tree_version':'fixture','engine_version':'synthetic'}}
        raise EngineError('Unknown test action '+action)
