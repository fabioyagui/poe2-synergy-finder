-- PoE2 Synergy Finder 0.17: visual geometry, detailed Calcs and bounded node comparisons.
-- All output is read from the loaded PoB. Does not save/mutate allocations.
local M = {}
local Tree = require('API.SynergyTree')
local PROTOCOL = 1
local function finite(v) return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function integer(v)
  local n=tonumber(v); assert(finite(n) and n>0 and n%1==0,'Indice/ID invalido.'); return n
end
local function scalars(t)
  local out={}; for k,v in pairs(t or {}) do
    if type(k)=='string' and (finite(v) or type(v)=='string' or type(v)=='boolean') then out[k]=v end
  end; return out
end
local function require_build()
  assert(build and build.spec and build.spec.nodes and build.calcsTab,'Carregue uma build PoB.');return build.spec
end
local function number_or(v, fallback) return finite(v) and v or fallback end
local function node_group(n,tree)
  if type(n.group)=='table' then return n.group end
  return tree.groups and tree.groups[n.g or n.group]
end
local function new_links(spec,n)
  local ids,seen={},{}
  local function add(v)
    if type(v)=='table' then v=v.id end
    v=tonumber(v)
    if finite(v) and v~=n.id and spec.nodes[v] and not seen[v] then ids[#ids+1]=v;seen[v]=true end
  end
  for _,v in pairs(n.linkedId or {}) do add(v) end
  for _,v in pairs(n.linked or {}) do add(v) end
  for _,v in pairs(n.connections or {}) do add(v) end
  table.sort(ids);return ids
end
function M.visual()
  local spec=require_build();local tree=spec.tree or {};local out=Tree.context()
  local scale=finite(tree.scaleImage) and tree.scaleImage or 1
  local by_id={};for _,r in ipairs(out.nodes) do by_id[r.id]=r end
  local count,missing=0,0
  local minx,miny,maxx,maxy=math.huge,math.huge,-math.huge,-math.huge
  for _,r in ipairs(out.nodes) do
    local n=spec.nodes[r.id];local g=node_group(n,tree)
    r.x=number_or(n.x,nil);r.y=number_or(n.y,nil)
    r.group_x=(g and finite(g.x)) and g.x*scale or nil;r.group_y=(g and finite(g.y)) and g.y*scale or nil
    r.orbit=number_or(n.o,number_or(n.orbit,nil));r.angle=number_or(n.angle,nil)
    r.orbit_radius=(r.orbit and tree.orbitRadii) and tree.orbitRadii[r.orbit+1] or nil
    if r.orbit_radius then r.orbit_radius=r.orbit_radius*scale end
    r.links=new_links(spec,n)
    r.unparsed=(n.unknown==true or n.extra==true)
    r.is_attribute=n.isAttribute==true
    r.icon_name=type(n.icon)=='string' and n.icon or nil -- no art files are downloaded
    if r.x and r.y then
      count=count+1;minx=math.min(minx,r.x);maxx=math.max(maxx,r.x);miny=math.min(miny,r.y);maxy=math.max(maxy,r.y)
    else missing=missing+1 end
  end
  assert(count>0,'O PoB nao expos coordenadas de nos. Use a lista de pontos; nenhuma posicao artificial foi criada.')
  local edges,seen={},{}
  for _,r in ipairs(out.nodes) do
    local n=spec.nodes[r.id]
    for _,oid in ipairs(r.links) do
      local o=by_id[oid]
      if o and o.x and o.y and r.x and r.y then
        local lo,hi=math.min(r.id,oid),math.max(r.id,oid);local key=lo..':'..hi
        if not seen[key] then
          seen[key]=true;local edge={a=r.id,b=oid}
          -- Preserve the connection's native circular orbit where present.
          local connection
          for _,c in pairs(n.connections or {}) do if c.id==oid then connection=c;break end end
          if connection and finite(connection.orbit) and connection.orbit~=0 and tree.orbitRadii then
            local radius=tree.orbitRadii[math.abs(connection.orbit)+1]
            if radius then radius=radius*scale end
            local dx,dy=o.x-r.x,o.y-r.y;local dist=math.sqrt(dx*dx+dy*dy)
            if radius and dist>0 and dist<2*radius then
              local perp=math.sqrt(radius*radius-dist*dist/4)*(connection.orbit>0 and 1 or -1)
              edge.cx=r.x+dx/2+perp*(dy/dist);edge.cy=r.y+dy/2-perp*(dx/dist);edge.radius=radius
            end
          elseif r.group_x and r.group_x==o.group_x and r.group_y==o.group_y and r.orbit==o.orbit and (r.orbit_radius or 0)>0 then
            edge.cx=r.group_x;edge.cy=r.group_y;edge.radius=r.orbit_radius
          end
          edges[#edges+1]=edge
        end
      end
    end
  end
  out.visual_protocol=PROTOCOL;out.edges=edges
  out.bounds={min_x=minx,max_x=maxx,min_y=miny,max_y=maxy}
  out.geometry={source='PoB PassiveSpec/PassiveTree coordinates + connections',positioned=count,missing=missing}
  out.class_name=spec.curClassName or (spec.curClass and spec.curClass.name)
  out.ascendancy_name=spec.curAscendClassName
  return out
end

local function select_skill(params)
  local spec=require_build();local gs=Tree.context().groups;local chosen
  if params.group_index then
    local idx=integer(params.group_index)
    for _,g in ipairs(gs) do if g.index==idx then chosen=g;break end end
  else
    for _,g in ipairs(gs) do if g.index==build.mainSocketGroup and g.enabled then chosen=g;break end end
    if not chosen then for _,g in ipairs(gs) do if g.enabled then chosen=g;break end end end
  end
  assert(chosen and chosen.enabled,'Escolha um grupo de skill ativo e reconhecido pelo PoB.')
  local ai=params.active_index and integer(params.active_index) or chosen.active_index
  local found
  for _,e in ipairs(chosen.effects) do if e.index==ai then found=e;break end end
  if not found and not params.active_index then found=chosen.effects[1];ai=found and found.index end
  assert(found,'Efeito ativo nao encontrado neste grupo.')
  local group=build.skillsTab.socketGroupList[chosen.index]
  build.mainSocketGroup=chosen.index;group.mainActiveSkill=ai;group.mainActiveSkillCalcs=ai
  build.calcsTab.input.skill_number=chosen.index
  return {group_index=chosen.index,active_index=ai,name=found.name,id=found.id},gs
end
-- Bounded JSON-safe snapshot. Ignore engine objects/functions/userdata, never
-- serialize the entire live build via a breakdown's item/node back reference.
local SKIP={item=true,node=true,actor=true,enemy=true,player=true,env=true,build=true,modDB=true,modList=true,parent=true,sourceInstance=true,srcInstance=true}
local function clean(v,depth,seen,budget)
  if finite(v) or type(v)=='string' or type(v)=='boolean' then return v end
  if type(v)~='table' then return nil end
  if depth>6 or budget.n>15000 then budget.truncated=true;return nil end
  if seen[v] then return nil end;seen[v]=true
  local out={}
  for k,x in pairs(v) do
    if (type(k)=='string' or (finite(k) and k>=1 and k%1==0)) and not SKIP[k] then
      budget.n=budget.n+1;if budget.n>15000 then budget.truncated=true;break end
      local copy=clean(x,depth+1,seen,budget);if copy~=nil then out[k]=copy end
    end
  end
  seen[v]=nil;return out
end
local MOD_FIELDS={
  AreaOfEffectMod={names={'AreaOfEffect','AreaOfEffectPrimary'},skill=true},
  AreaOfEffectRadiusMetres={names={'AreaOfEffect','AreaOfEffectPrimary'},skill=true},
  Duration={names={'Duration','SkillEffectDuration'},skill=true},
  Cooldown={names={'CooldownRecovery'},skill=true},
  Life={names={'Life'}},EnergyShield={names={'EnergyShield'}},Mana={names={'Mana'}},
  Armour={names={'Armour'}},Evasion={names={'Evasion'}},
  FireResist={names={'FireResist'}},ColdResist={names={'ColdResist'}},LightningResist={names={'LightningResist'}},ChaosResist={names={'ChaosResist'}},
  Str={names={'Str'}},Dex={names={'Dex'}},Int={names={'Int'}},
}
local function modifier_rows(actor,key)
  local definition=MOD_FIELDS[key];if not definition then return {},false end
  local skill=actor.mainSkill;local store=definition.skill and skill and skill.skillModList or actor.modDB
  local cfg=definition.skill and skill and skill.skillCfg or {}
  if not store or not store.Tabulate then return {},false end
  local rows={}
  for _,tp in ipairs({'BASE','INC','MORE'}) do
    local ok,entries=pcall(function()return store:Tabulate(tp,cfg,unpack(definition.names))end)
    if not ok then return rows,false end
    for _,entry in ipairs(entries or {}) do
      local mod=entry.mod or entry;local val=entry.value
      if val==nil then val=mod.value end
      rows[#rows+1]={name=mod.name,type=mod.type or tp,value=(finite(val) or type(val)=='boolean') and val or tostring(val),source=type(mod.source)=='string' and mod.source or nil}
    end
  end
  return rows,true
end
function M.calcs(params)
  params=params or {};local spec=require_build();local stamp=Tree.state().fingerprint
  local selected,gs=select_skill(params)
  local modes={UNBUFFED=true,BUFFED=true,COMBAT=true,EFFECTIVE=true}
  local mode=params.buff_mode or build.calcsTab.input.misc_buffMode or 'EFFECTIVE'
  assert(modes[mode],'Modo de buffs invalido.');build.calcsTab.input.misc_buffMode=mode
  build.calcsTab:BuildOutput()
  local env=build.calcsTab.calcsEnv;assert(env and env.player,'PoB nao retornou calcsEnv.player.')
  local who=params.actor or 'player';assert(who=='player' or who=='minion','Ator invalido.')
  local actor=env[who];assert(actor and actor.output,'Esta skill nao tem calculos para esse ator/minion.')
  local budget={n=0,truncated=false};local breakdowns={}
  for key,value in pairs(actor.breakdown or {}) do
    if type(key)=='string' then breakdowns[key]=clean(value,0,{},budget) end
  end
  local sources={};local available={}
  for key in pairs(MOD_FIELDS) do local rows,ok=modifier_rows(actor,key);sources[key]=rows;available[key]=ok end
  local skill=actor.mainSkill;local flags={};local support_names={};local warnings={}
  if skill then
    local effect=skill.activeEffect;local ss=effect and (effect.statSetCalcs or effect.statSet)
    flags=scalars((ss and ss.skillFlags) or skill.skillFlags)
    for _,e in ipairs(skill.effectList or {}) do
      if e.grantedEffect and e.grantedEffect.support then
        local instance=e.srcInstance;local gd=instance and instance.gemData
        support_names[#support_names+1]=(gd and gd.name) or (instance and instance.nameSpec) or e.grantedEffect.name or e.grantedEffect.id
      end
    end
  end
  assert(Tree.state().fingerprint==stamp,'Alocacoes mudaram durante leitura: resultado descartado.')
  local outputs=scalars(actor.output);local main=scalars(build.calcsTab.mainOutput)
  local bdkeys={};for key in pairs(breakdowns) do bdkeys[#bdkeys+1]=key end;table.sort(bdkeys)
  return {protocol=PROTOCOL,workbench_protocol=PROTOCOL,kind='calcs',skill=selected,groups=gs,
    output=outputs,sidebar_output=main,breakdowns=breakdowns,breakdown_keys=bdkeys,
    modifier_sources=sources,modifier_sources_available=available,
    selection={buff_mode=mode,actor=who,minion_available=env.minion~=nil},
    skill_flags=flags,supports=support_names,configuration=scalars(build.configTab and build.configTab.input),
    detail_truncated=budget.truncated,source='PoB calcsEnv.'..who..'.output / breakdown',
    tree_version=spec.treeVersion,engine_version=launch and launch.versionNumber,
    allocation_unchanged=true,point_budget_verified=false}
end

-- Compare a bounded sample of reachable normal-tree nodes using full paths.
-- This is not a full-tree optimizer, and has no hand-authored power score.
local METRICS={CombinedDPS=1,IgniteDPS=1,Life=1,EnergyShield=1,Armour=1,Evasion=1,Mana=1,ManaRegen=1,
  AreaOfEffectMod=1,AreaOfEffectRadiusMetres=1,Duration=1,Cooldown=-1,ManaCost=-1}
local function same(a,b)
  if finite(a) and finite(b) then return math.abs(a-b)<=1e-7*math.max(1,math.abs(a),math.abs(b)) end
  return a==b
end
function M.suggest(params)
  params=params or {};local spec=require_build();local stamp=Tree.state().fingerprint
  assert(params.fingerprint==stamp,'A arvore mudou. Recarregue antes de buscar sugestoes.')
  local key=params.metric or 'Life';assert(METRICS[key],'Metrica nao permitida neste teste.')
  local maxp=integer(params.max_points or 2);assert(maxp<=5,'Escolha ate 5 pontos por caminho.')
  local limit=integer(params.limit or 12);assert(limit<=16,'Avaliacao limitada a 16 caminhos por vez.')
  local query=string.lower(tostring(params.query or ''));assert(#query<=100,'Busca muito longa.')
  local selected=select_skill(params);build.calcsTab:BuildOutput()
  local calc,base=build.calcsTab:GetMiscCalculator();assert(type(calc)=='function' and type(base)=='table','Calculadora indisponivel.')
  local before=scalars(base);assert(finite(before[key]),'O PoB nao retornou a metrica escolhida. Nada foi tratado como zero.')
  local ctrl=scalars(calc({},true));local control={}
  local keys={};for k in pairs(before)do keys[k]=true end;for k in pairs(ctrl)do keys[k]=true end
  for k in pairs(keys)do if not same(before[k],ctrl[k])then control[#control+1]=k end end
  assert(#control==0,'Controle A/A divergiu: sugestoes nao publicadas.')
  local all={}
  for _,n in pairs(spec.nodes) do
    if not spec.allocNodes[n.id] and not n.ascendancyName and not n.unknown and not n.extra and n.type~='ClassStart' and n.type~='OnlyImage' then
      local text=string.lower((n.name or '')..' '..table.concat(n.sd or {},' '))
      if query=='' or string.find(text,query,1,true) then
        local ok,plan=pcall(Tree.plan,{node_id=n.id,mode='path'})
        if ok and plan.path_checked and plan.total_delta<=maxp and plan.ascendancy_delta==0 then
          all[#all+1]={node_id=n.id,plan=plan}
        end
      end
    end
  end
  table.sort(all,function(a,b)if a.plan.total_delta==b.plan.total_delta then return a.node_id<b.node_id end;return a.plan.total_delta<b.plan.total_delta end)
  local evaluated,rows,errors=0,{},{}
  for i,candidate in ipairs(all) do
    if evaluated>=limit then break end;evaluated=evaluated+1
    local override={addNodes={}};for _,id in ipairs(candidate.plan.add_ids)do override.addNodes[spec.nodes[id]]=true end
    local ok,value=pcall(function()return scalars(calc(override,true))end)
    if ok and finite(value[key])then
      local delta=value[key]-before[key];rows[#rows+1]={node_id=candidate.node_id,plan=candidate.plan,
        before=before[key],after=value[key],delta=delta,per_point=delta/candidate.plan.total_delta,
        benefit_per_point=METRICS[key]*delta/candidate.plan.total_delta,baseline=before,variant=value}
    else errors[#errors+1]={node_id=candidate.node_id,error=ok and 'Metrica ausente neste resultado' or tostring(value)} end
  end
  table.sort(rows,function(a,b)if a.benefit_per_point==b.benefit_per_point then return a.node_id<b.node_id end;return a.benefit_per_point>b.benefit_per_point end)
  assert(Tree.state().fingerprint==stamp,'Alocacoes mudaram: resultado descartado.')
  return {protocol=PROTOCOL,workbench_protocol=PROTOCOL,kind='suggestions',metric=key,direction=METRICS[key],rows=rows,errors=errors,
    eligible=#all,evaluated=evaluated,limit=limit,max_points=maxp,query=query,skill=selected,
    sample_order='Menor custo de caminho, depois ID; ranking apenas entre os caminhos avaliados.',
    control_differences=control,point_budget_verified=false,tree_version=spec.treeVersion,allocation_unchanged=true}
end
function M.install(handlers)
  local function wrap(fn)return function(params)local ok,r=pcall(fn,params or {});if not ok then return {ok=false,error=tostring(r)}end;return {ok=true,result=r}end end
  handlers.sf_workbench_visual=wrap(M.visual);handlers.sf_workbench_calcs=wrap(M.calcs);handlers.sf_workbench_suggest=wrap(M.suggest)
end
return M
