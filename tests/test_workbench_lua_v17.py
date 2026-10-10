"""Run our entire Lua workbench module against a synthetic PoB-shaped environment.
These verify code behavior, NOT game accuracy or a Windows PoB installation.
"""
import ctypes
import ctypes.util
import json
from pathlib import Path
import unittest
from tests.test_tree_lua_v16 import FIXTURE, LIB, MODULE
WORKBENCH=Path(__file__).resolve().parents[1]/'src/lua/synergy_workbench.lua'
PRELUDE=r'''
unpack=table.unpack or unpack
package.preload['API.SynergyTree']=function()return M end
local group={x=0,y=0}
for id,n in pairs(nodes)do n.x=id*100;n.y=(id%3)*100;n.group=group;n.g=1;n.o=1;n.linkedId={} end
nodes[2].linkedId={3};nodes[3].linkedId={2,4};nodes[4].linkedId={3}
spec.tree={groups={[1]=group},orbitRadii={0,82}}
local player={output={Life=112,Mana=0,AreaOfEffectMod=1.08,UnknownFuture=3},
 breakdown={Life={'100 base','+12 from points'},SomeTable={rowList={{v=112,source='Tree:2'}},colList={{key='v',label='Life'}}}},
 mainSkill={skillModList={},skillCfg={},activeEffect={statSetCalcs={skillFlags={area=true}}},effectList={}}}
function player.mainSkill.skillModList:Tabulate(tp,cfg,...) if tp=='INC' then return {{mod={name='AreaOfEffect',type='INC',value=8,source='Tree:2'}}} end return {} end
player.modDB=player.mainSkill.skillModList
build.configTab={input={enemyIsBoss=true}}
function build.calcsTab:BuildOutput()
 self.mainOutput=player.output;self.calcsEnv={player=player}
end
local W=dofile(WB_MODULE)
'''

@unittest.skipUnless(LIB,'Lua 5.4 unavailable')
class WorkbenchLuaTests(unittest.TestCase):
    def execute(self,body):
        lib=ctypes.CDLL(LIB);lib.luaL_newstate.restype=ctypes.c_void_p
        lib.luaL_openlibs.argtypes=[ctypes.c_void_p];lib.luaL_loadstring.argtypes=[ctypes.c_void_p,ctypes.c_char_p];lib.luaL_loadstring.restype=ctypes.c_int
        lib.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_longlong,ctypes.c_void_p];lib.lua_pcallk.restype=ctypes.c_int
        lib.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p];lib.lua_tolstring.restype=ctypes.c_char_p;lib.lua_close.argtypes=[ctypes.c_void_p]
        state=lib.luaL_newstate();lib.luaL_openlibs(state)
        try:
            code=('MODULE='+json.dumps(str(MODULE))+'\nWB_MODULE='+json.dumps(str(WORKBENCH))+'\n'+FIXTURE+'\n'+PRELUDE+'\n'+body).encode()
            result=lib.luaL_loadstring(state,code)
            if result==0:result=lib.lua_pcallk(state,0,0,0,0,None)
            self.assertEqual(result,0,(lib.lua_tolstring(state,-1,None)or b'').decode(errors='replace'))
        finally:lib.lua_close(state)
    def test_geometry_real_coordinates_not_layout_guess(self):self.execute("local r=W.visual();assert(r.visual_protocol==1 and #r.nodes==9 and #r.edges==2);assert(r.nodes[1].x==100);assert(r.bounds.max_x==900)")
    def test_geometry_respects_pob_scale(self):self.execute("spec.tree.scaleImage=0.5;local r=W.visual();assert(r.edges[1].radius==41)")
    def test_missing_geometry_rejected(self):self.execute("for _,n in pairs(nodes)do n.x=nil;n.y=nil end;assert(not pcall(W.visual))")
    def test_edges_deduped(self):self.execute("nodes[2].linked={nodes[3]};local r=W.visual();assert(#r.edges==2)")
    def test_known_orbit_geometry(self):self.execute("local r=W.visual();assert(r.edges[1].cx==0 and r.edges[1].radius==82)")
    def test_disconnected_nodes_not_invented(self):self.execute("nodes[2].linkedId={};nodes[3].linkedId={};nodes[4].linkedId={};assert(#W.visual().edges==0)")
    def test_calc_zero_preserved(self):self.execute("local r=W.calcs({});assert(r.output.Mana==0 and r.output.UnknownFuture==3)")
    def test_calcs_skill_and_mode_applied(self):self.execute("local r=W.calcs({group_index=1,active_index=1,buff_mode='UNBUFFED'});assert(r.skill.name=='Fixture Skill');assert(build.calcsTab.input.misc_buffMode=='UNBUFFED')")
    def test_unknown_actor_or_mode_rejected(self):self.execute("assert(not pcall(W.calcs,{actor='other'}));assert(not pcall(W.calcs,{buff_mode='invalid'}))")
    def test_missing_minion_rejected(self):self.execute("assert(not pcall(W.calcs,{actor='minion'}))")
    def test_breakdown_lines_and_tables_preserved(self):self.execute("local r=W.calcs({});assert(r.breakdowns.Life[2]=='+12 from points');assert(r.breakdowns.SomeTable.rowList[1].v==112)")
    def test_no_cyclic_engine_object_serialized(self):self.execute("player.breakdown.Life.item=build;player.breakdown.Life.fn=function()end;player.breakdown.Life.self=player.breakdown.Life;local r=W.calcs({});assert(r.breakdowns.Life.item==nil and r.breakdowns.Life.fn==nil and r.breakdowns.Life.self==nil)")
    def test_modifier_sources_from_engine(self):self.execute("local r=W.calcs({});assert(r.modifier_sources.AreaOfEffectMod[1].source=='Tree:2');assert(r.modifier_sources_available.AreaOfEffectMod)")
    def test_deep_breakdown_marks_truncation(self):self.execute("local t=player.breakdown;for i=1,20 do t.deep={};t=t.deep end;local r=W.calcs({});assert(r.detail_truncated)")
    def test_suggestions_compare_full_path_cost(self):self.execute("local r=W.suggest({metric='Life',max_points=2,limit=12,fingerprint=M.state().fingerprint});assert(r.eligible==2 and r.evaluated==2);assert(r.rows[1].node_id==4);assert(r.rows[1].delta==50 and r.rows[1].per_point==25)")
    def test_suggestions_limit_scope(self):self.execute("local r=W.suggest({metric='Life',max_points=2,limit=1,fingerprint=M.state().fingerprint});assert(r.evaluated==1 and r.eligible==2 and r.rows[1].node_id==3)")
    def test_suggestions_do_not_allocate(self):self.execute("local before=M.state().fingerprint;W.suggest({metric='Life',max_points=2,fingerprint=before});assert(M.state().fingerprint==before)")
    def test_aa_control_failure_rejects_ranking(self):self.execute("function build.calcsTab:GetMiscCalculator()return function()return {Life=120}end,{Life=100}end;assert(not pcall(W.suggest,{metric='Life',fingerprint=M.state().fingerprint}))")
    def test_missing_metric_not_zero(self):self.execute("assert(not pcall(W.suggest,{metric='IgniteDPS',fingerprint=M.state().fingerprint}))")
    def test_future_unknown_action_contract(self):self.execute("local h={};W.install(h);assert(type(h.sf_workbench_visual)=='function');assert(h.sf_workbench_calcs({actor='minion'}).ok==false)")
    def test_unavailable_point_budget_not_claimed(self):self.execute("local r=W.suggest({metric='Life',fingerprint=M.state().fingerprint});assert(r.point_budget_verified==false)")

if __name__=='__main__':unittest.main()
