-- Synergy Finder: read-only passive-tree experiments (protocol 1).
-- Uses the PoB instance supplied by the user's local headless bridge.
-- No allocations, items, or gems are written by this module.
local M = {}
local PROTOCOL = 1
local MAX_CHANGES = 50

local function finite(v)
  return type(v) == 'number' and v == v and v ~= math.huge and v ~= -math.huge
end
local function scalars(t)
  local out = {}
  for k, v in pairs(t or {}) do
    if type(k) == 'string' and (finite(v) or type(v) == 'boolean' or type(v) == 'string') then out[k] = v end
  end
  return out
end
local function require_build()
  assert(build and build.spec and build.spec.nodes and build.calcsTab, 'Carregue um XML PoB antes de simular pontos.')
  return build.spec
end
local function integer(v)
  local n = tonumber(v)
  assert(finite(n) and n >= 0 and n % 1 == 0, 'ID/indice invalido.')
  return n
end
local function fingerprint(spec)
  local rows = {}
  for id, n in pairs(spec.allocNodes or {}) do rows[#rows+1] = tostring(id)..':'..tostring(n.allocMode or 0) end
  table.sort(rows)
  return tostring(spec.treeVersion)..'|'..tostring(spec.curClassId)..'|'..tostring(spec.curAscendClassId)..'|'..table.concat(rows, ',')
end
local function ids_from(list, predicate)
  local ids, seen = {}, {}
  for _, n in pairs(list or {}) do
    if type(n) == 'table' and finite(tonumber(n.id)) and (not predicate or predicate(n)) and not seen[n.id] then
      ids[#ids+1] = tonumber(n.id); seen[n.id] = true
    end
  end
  table.sort(ids)
  return ids
end
local function block_reason(spec, n)
  if n.type == 'ClassStart' or n.type == 'AscendClassStart' then return 'O inicio da classe nao pode ser alterado neste teste.' end
  if (n.allocMode or 0) ~= 0 then return 'Ponto exclusivo de weapon set: edicao separada ainda nao suportada.' end
  if n.isFreeAllocate or n.isGrantedPassive then return 'Ponto concedido por outra fonte: altere a fonte, nao este ponto.' end
  if n.isMultipleChoiceOption or n.isMultipleChoice or n.unlockConstraint then return 'Este ponto possui escolhas ou desbloqueios especiais nao validados aqui.' end
  if n.type ~= 'Normal' and n.type ~= 'Notable' and n.type ~= 'Keystone' then return 'Este tipo exige uma operacao propria (socket, mastery ou outro tipo especial).' end
  if n.ascendancyName then
    local current = spec.curAscendClassName
    if not current and spec.curClass and spec.curClass.classes then
      local cls = spec.curClass.classes[spec.curAscendClassId]
      current = cls and cls.name
    end
    if n.ascendancyName ~= current then return 'Apenas a ascendencia atual pode ser testada neste modulo.' end
  end
end
local function node_record(spec, n)
  local lines = {}
  for _, line in ipairs(n.sd or {}) do if type(line) == 'string' then lines[#lines+1] = line end end
  local reason = block_reason(spec, n)
  local distance = finite(n.pathDist) and n.pathDist < 100000 and n.pathDist or nil
  return {
    id = n.id, name = n.name or ('No '..tostring(n.id)), kind = n.type or 'Unknown', stats = lines,
    allocated = spec.allocNodes[n.id] ~= nil, allocation_mode = n.allocMode or 0,
    ascendancy = n.ascendancyName, path_distance = distance,
    dependent_count = #(n.depends or {}), editable = reason == nil, blocked_reason = reason,
  }
end
local function counts(spec)
  if type(spec.CountAllocNodes) ~= 'function' then return {known=false} end
  local ok, ordinary, ascendancy, secondary, sockets, w1, w2 = pcall(spec.CountAllocNodes, spec)
  if not ok then return {known=false} end
  return {known=true, ordinary=ordinary, ascendancy=ascendancy, secondary_ascendancy=secondary,
    sockets=sockets, weapon_set_1=w1, weapon_set_2=w2, source='PoB CountAllocNodes'}
end
local function groups()
  local out = {}
  for i, g in ipairs(build.skillsTab and build.skillsTab.socketGroupList or {}) do
    local effects = {}
    for j, effect in ipairs(g.displaySkillList or {}) do
      local ge = effect.activeEffect and effect.activeEffect.grantedEffect
      if ge then effects[#effects+1] = {index=j, name=ge.name or ge.id, id=ge.id} end
    end
    if #effects > 0 then out[#out+1] = {index=i, label=g.label, enabled=g.enabled ~= false,
      active_index=g.mainActiveSkill or 1, effects=effects} end
  end
  return out
end
function M.state()
  local spec = require_build()
  return {protocol=PROTOCOL, fingerprint=fingerprint(spec), tree_version=spec.treeVersion}
end
function M.context()
  local spec = require_build()
  local nodes = {}
  for _, n in pairs(spec.nodes) do
    if finite(n.id) then nodes[#nodes+1] = node_record(spec, n) end
  end
  table.sort(nodes, function(a,b) return a.id < b.id end)
  local weapon = build.itemsTab and build.itemsTab.activeItemSet
  return {
    protocol=PROTOCOL, fingerprint=fingerprint(spec), nodes=nodes, counts=counts(spec), groups=groups(),
    selected_group=build.mainSocketGroup, tree_version=spec.treeVersion,
    engine_version=launch and launch.versionNumber or nil,
    active_weapon_set=weapon and (weapon.useSecondWeaponSet and 2 or 1) or nil,
    point_budget_verified=false,
  }
end
local function allocation_path(spec, node)
  -- Prefer the engine's explicit normal-pool API when available.
  if type(spec.GetAllocationPath) == 'function' then
    return spec:GetAllocationPath(node, 0, false), 'PoB GetAllocationPath'
  end
  -- Older PoB: node.path is the engine's precomputed path. Never promote a weapon-set branch silently.
  if node.pathRoot and (node.pathRoot.allocMode or 0) ~= 0 then return nil, 'Raiz exclusiva de weapon set' end
  return node.path, 'PoB node.path'
end
function M.plan(params)
  local spec = require_build()
  local node = spec.nodes[integer(params.node_id)]
  assert(node, 'O ponto nao existe na arvore deste PoB.')
  local reason = block_reason(spec, node)
  assert(not reason, reason)
  local mode = params.mode or 'path'
  assert(mode == 'path' or mode == 'isolated', 'Modo invalido.')
  local allocated = spec.allocNodes[node.id] ~= nil
  local needed, path_source, connected = {}, nil, false
  if allocated then
    assert(type(node.depends) == 'table', 'PoB nao expos as dependencias deste ponto.')
    needed = ids_from(node.depends, function(n) return spec.allocNodes[n.id] ~= nil end)
    local has = false
    for _, id in ipairs(needed) do if id == node.id then has = true end end
    if not has then needed[#needed+1] = node.id; table.sort(needed) end
    connected = #needed == 1
    path_source = 'PoB node.depends'
  else
    local path
    path, path_source = allocation_path(spec, node)
    if path then needed = ids_from(path, function(n) return spec.allocNodes[n.id] == nil end) end
    local has = false
    for _, id in ipairs(needed) do if id == node.id then has = true end end
    if path and not has then needed[#needed+1] = node.id; table.sort(needed) end
    connected = path ~= nil and #needed == 1
    if mode == 'path' then assert(path, 'PoB nao encontrou caminho normal para este ponto. O modo isolado e apenas uma hipotese matematica.') end
  end
  local changed = mode == 'path' and needed or {node.id}
  assert(#changed > 0 and #changed <= MAX_CHANGES, 'O teste deve alterar entre 1 e 50 pontos. Escolha um ponto mais proximo.')
  local rows, normal, asc = {}, 0, 0
  for _, id in ipairs(changed) do
    local n = spec.nodes[id]
    assert(n, 'Caminho contem um ponto desconhecido.')
    local block = block_reason(spec, n)
    assert(not block, 'Caminho/dependencia inclui ponto especial: '..(n.name or tostring(id))..'. '..(block or ''))
    rows[#rows+1] = node_record(spec, n)
    if n.ascendancyName then asc = asc + 1 else normal = normal + 1 end
  end
  local sign = allocated and -1 or 1
  return {protocol=PROTOCOL, fingerprint=fingerprint(spec), target=node_record(spec,node),
    action=allocated and 'remove' or 'add', mode=mode, changes=rows,
    add_ids=allocated and {} or changed, remove_ids=allocated and changed or {},
    ordinary_delta=sign*normal, ascendancy_delta=sign*asc, total_delta=sign*#changed,
    required_ids=needed, path_source=path_source,
    path_checked=mode=='path' or connected, isolated_hypothesis=mode=='isolated' and not connected,
    point_budget_verified=false, tree_version=spec.treeVersion,
  }
end
local function scalar_equal(a,b)
  if type(a) == 'number' and type(b) == 'number' then return math.abs(a-b) <= 1e-7 * math.max(1,math.abs(a),math.abs(b)) end
  return a == b
end
local function differences(a,b)
  local keys, out = {}, {}
  for k in pairs(a) do keys[k] = true end
  for k in pairs(b) do keys[k] = true end
  for k in pairs(keys) do if not scalar_equal(a[k],b[k]) then out[#out+1] = k end end
  table.sort(out); return out
end
function M.compare(params)
  local spec = require_build()
  local before_stamp = fingerprint(spec)
  assert(params.fingerprint == before_stamp, 'A arvore mudou. Recarregue o simulador.')
  local plan = M.plan(params)
  local index = integer(params.group_index)
  local g = build.skillsTab.socketGroupList[index]
  assert(g and g.enabled ~= false, 'Selecione um grupo de skill ativo.')
  local ai = integer(params.active_index)
  assert(g.displaySkillList and g.displaySkillList[ai], 'Selecione um efeito ativo reconhecido pelo PoB.')
  -- These selections are transient; the Python transaction reloads the original XML in all cases.
  build.mainSocketGroup = index
  g.mainActiveSkill = ai
  g.mainActiveSkillCalcs = ai
  build.calcsTab.input.skill_number = index
  build.calcsTab:BuildOutput()
  local effect = g.displaySkillList[ai]
  local ge = effect and effect.activeEffect and effect.activeEffect.grantedEffect
  local calc, base = build.calcsTab:GetMiscCalculator()
  assert(type(calc) == 'function' and type(base) == 'table', 'Calculadora nativa de pontos indisponivel.')
  -- Freeze every snapshot before the next calculation (no live-table aliasing).
  local baseline = scalars(base)
  local control = scalars(calc({}, true))
  local override = {addNodes={}, removeNodes={}}
  for _, id in ipairs(plan.add_ids) do override.addNodes[spec.nodes[id]] = true end
  for _, id in ipairs(plan.remove_ids) do override.removeNodes[spec.nodes[id]] = true end
  local variant = scalars(calc(override, true))
  local after_stamp = fingerprint(spec)
  assert(after_stamp == before_stamp, 'O motor alterou alocacoes durante um teste somente-leitura; resultado descartado.')
  return {protocol=PROTOCOL, plan=plan, baseline=baseline, variant=variant,
    control_differences=differences(baseline,control), allocation_unchanged=true,
    skill={group_index=index, active_index=ai, name=ge and ge.name, id=ge and ge.id},
    calculator='PoB GetMiscCalculator / addNodes-removeNodes', tree_version=spec.treeVersion,
    engine_version=launch and launch.versionNumber or nil,
  }
end
function M.install(handlers)
  local function wrap(fn)
    return function(params)
      local ok, result = pcall(fn, params or {})
      if not ok then return {ok=false, error=tostring(result)} end
      return {ok=true, result=result}
    end
  end
  handlers.sf_tree_state=wrap(M.state)
  handlers.sf_tree_context=wrap(M.context)
  handlers.sf_tree_plan=wrap(M.plan)
  handlers.sf_tree_compare=wrap(M.compare)
end
return M
