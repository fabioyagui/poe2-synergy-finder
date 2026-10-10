"""Execute the extension as Lua, using a synthetic PoB-contract fixture.

These are not live PoB DPS tests. Lua 5.4 shared library is optional on Windows.
The distributed extension itself uses Lua 5.1-compatible syntax.
"""
import ctypes
import ctypes.util
import json
from pathlib import Path
import unittest

LIB=ctypes.util.find_library('lua5.4')
MODULE=Path(__file__).resolve().parents[1]/'src/lua/synergy_tree.lua'
FIXTURE=r'''
local nodes={}
local function node(id, name, tp, alloc, life)
 local n={id=id,name=name,type=tp,alloc=alloc,allocMode=0,sd={'+'..tostring(life or 0)..' Life'},depends={},path={},pathDist=1,life=life or 0}
 nodes[id]=n;return n
end
local start=node(1,'Start','ClassStart',true)
local allocated=node(2,'Allocated','Normal',true,10)
local close=node(3,'Close','Normal',false,20)
local far=node(4,'Far','Notable',false,30)
local ws=node(5,'Weapon','Normal',true,1);ws.allocMode=1
local asc=node(6,'Asc','Notable',false,5);asc.ascendancyName='Current'
local other=node(7,'Other','Notable',false);other.ascendancyName='Other'
local socket=node(8,'Socket','Socket',false)
local dependent=node(9,'Dependent','Normal',true,2)
allocated.depends={allocated,dependent};dependent.depends={dependent}
close.path={close};far.path={close,far};asc.path={asc}
local spec={nodes=nodes,allocNodes={[1]=start,[2]=allocated,[5]=ws,[9]=dependent},treeVersion='fixture',curClassId=0,curAscendClassId=1,curAscendClassName='Current'}
function spec:CountAllocNodes() return 3,0,0,0,1,0 end
local ge={name='Fixture Skill',id='fixture'}
local g={enabled=true,mainActiveSkill=1,displaySkillList={{activeEffect={grantedEffect=ge}}}}
build={spec=spec,skillsTab={socketGroupList={g}},calcsTab={input={}},itemsTab={activeItemSet={}}}
function build.calcsTab:BuildOutput() end
function build.calcsTab:GetMiscCalculator()
 local shared={Life=112,Mana=40,TotalDPS=100,Nested={a=1}}
 local function calc(override)
   local life=112
   for n in pairs(override.addNodes or {}) do life=life+n.life end
   for n in pairs(override.removeNodes or {}) do life=life-n.life end
   shared.Life=life
   return shared
 end
 return calc,shared
end
launch={versionNumber='fixture'}
local M=dofile(MODULE)
'''

@unittest.skipUnless(LIB, 'Lua shared library not installed; synthetic Lua execution tests skipped')
class LuaExecutionTests(unittest.TestCase):
    def execute(self, script):
        l=ctypes.CDLL(LIB)
        l.luaL_newstate.restype=ctypes.c_void_p
        l.luaL_openlibs.argtypes=[ctypes.c_void_p]
        l.luaL_loadstring.argtypes=[ctypes.c_void_p,ctypes.c_char_p];l.luaL_loadstring.restype=ctypes.c_int
        l.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_longlong,ctypes.c_void_p];l.lua_pcallk.restype=ctypes.c_int
        l.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p];l.lua_tolstring.restype=ctypes.c_char_p
        l.lua_close.argtypes=[ctypes.c_void_p]
        state=l.luaL_newstate();l.luaL_openlibs(state)
        try:
            code=('MODULE='+json.dumps(str(MODULE))+'\n'+FIXTURE+'\n'+script).encode()
            status=l.luaL_loadstring(state,code)
            if status==0:status=l.lua_pcallk(state,0,0,0,0,None)
            self.assertEqual(status,0,(l.lua_tolstring(state,-1,None) or b'').decode(errors='replace'))
        finally:l.lua_close(state)
    def test_actual_lua_module_loads_context(self):
        self.execute("local c=M.context(); assert(#c.nodes==9 and #c.groups==1 and c.counts.ordinary==3)")
    def test_add_complete_route_from_engine_path(self):
        self.execute("local p=M.plan({node_id=4,mode='path'}); assert(#p.add_ids==2 and p.path_checked and p.total_delta==2)")
    def test_isolated_add_is_hypothesis(self):
        self.execute("local p=M.plan({node_id=4,mode='isolated'}); assert(#p.add_ids==1 and p.isolated_hypothesis and not p.path_checked)")
    def test_removal_includes_dependents(self):
        self.execute("local p=M.plan({node_id=2}); assert(#p.remove_ids==2 and p.total_delta==-2)")
    def test_removal_leaf_single_point(self):
        self.execute("local p=M.plan({node_id=9,mode='isolated'}); assert(#p.remove_ids==1 and p.path_checked)")
    def test_locked_and_special_nodes_rejected(self):
        self.execute("for _,id in ipairs({1,5,7,8,999}) do assert(not pcall(M.plan,{node_id=id})) end")
    def test_path_through_weapon_set_rejected(self):
        self.execute("nodes[4].path={nodes[5],nodes[4]}; nodes[5].alloc=false; spec.allocNodes[5]=nil; assert(not pcall(M.plan,{node_id=4}))")
    def test_ascendancy_separate_cost(self):
        self.execute("local p=M.plan({node_id=6}); assert(p.ordinary_delta==0 and p.ascendancy_delta==1)")
    def test_native_override_and_frozen_baseline(self):
        self.execute("local s=M.state();local r=M.compare({node_id=3,group_index=1,active_index=1,fingerprint=s.fingerprint}); assert(r.baseline.Life==112 and r.variant.Life==132 and r.allocation_unchanged);assert(#r.control_differences==0);assert(M.state().fingerprint==s.fingerprint)")
    def test_repeated_identical_comparison(self):
        self.execute("local s=M.state();local p={node_id=3,group_index=1,active_index=1,fingerprint=s.fingerprint};local a=M.compare(p);local b=M.compare(p);assert(a.variant.Life==b.variant.Life and b.baseline.Life==112)")
    def test_removal_calculates_loss(self):
        self.execute("local r=M.compare({node_id=2,group_index=1,active_index=1,fingerprint=M.state().fingerprint});assert(r.variant.Life==100)")
    def test_stale_tree_rejected(self):
        self.execute("assert(not pcall(M.compare,{node_id=3,group_index=1,active_index=1,fingerprint='wrong'}))")
    def test_handler_errors_are_reported(self):
        self.execute("local h={};M.install(h);local r=h.sf_tree_plan({node_id=999});assert(r.ok==false and type(r.error)=='string')")
    def test_no_path_fails_closed(self):
        self.execute("nodes[4].path=nil;assert(not pcall(M.plan,{node_id=4,mode='path'}));local p=M.plan({node_id=4,mode='isolated'});assert(p.isolated_hypothesis)")
    def test_uses_modern_explicit_normal_allocation_api(self):
        self.execute("function spec:GetAllocationPath(n,mode,only) assert(mode==0 and only==false);return {nodes[3],n} end;local p=M.plan({node_id=4});assert(p.path_source=='PoB GetAllocationPath')")
