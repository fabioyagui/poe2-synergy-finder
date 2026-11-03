-- PoE2 Synergy Finder: hipotese de patch. Troca numeros de gems na memoria do PoB 2 (data.skills) para medir
-- o que as notas de um patch dizem antes de o PoB novo sair. Nada vai para disco; cada aplicacao restaura os
-- valores originais antes de aplicar a nova lista, e uma lista vazia volta tudo ao PoB instalado.
--
-- Onde o PoB 2 le cada numero (Modules/CalcActiveSkill.lua, CalcOffence.lua, CalcTools.lua):
--   grantedEffect.castTime                      tempo de uso (CalcOffence: output.Time / base cast time)
--   grantedEffect.levels[n].cooldown/storedUses/critChance/baseMultiplier/attackSpeedMultiplier/damageMultiplier/attackTime
--   grantedEffect.levels[n].cost.Mana           custo de mana; spiritReservationFlat = reserva de Spirit
--   statSets[i].levels[n][campo]                sobrepoe o nivel do grantedEffect quando existe (CalcActiveSkill 792-797)
--   statSets[i].baseEffectiveness/incrementalEffectiveness  dano base por nivel das spells (CalcTools 165-169)
--   statSets[i].levels[n][indice]               stats por nivel (statSets[i].stats[indice]), ex.: dano fixo da skill
--   statSets[i].constantStats                   stats fixos
local M = {}
local PROTOCOL = 1
local LEVEL_FIELDS = { cooldown = true, critChance = true, baseMultiplier = true, storedUses = true,
  damageMultiplier = true, attackSpeedMultiplier = true, attackTime = true, spiritReservationFlat = true }
local SET_FIELDS = { baseEffectiveness = true, incrementalEffectiveness = true }
local saved = {}   -- [grantedEffect] = { castTime, levels = {[n] = {campo = v}}, sets = {[statSet] = {...}} }
local active = {}  -- relatorio da ultima aplicacao

local function finite(v) return type(v) == 'number' and v == v and v ~= math.huge and v ~= -math.huge end

local function find_effect(name)
  if data.skills[name] then return data.skills[name] end
  local best
  for id, ge in pairs(data.skills) do
    if ge.name == name and not ge.support then
      -- Entre homonimos (ex.: skill do jogador e a do minion) prefere a do jogador.
      if not best or (id:sub(-6) == 'Player' and best.id:sub(-6) ~= 'Player') then best = ge end
    end
  end
  return best
end

local function restore_all()
  for ge, s in pairs(saved) do
    if s.castTime ~= nil then ge.castTime = s.castTime end
    for n, fields in pairs(s.levels) do
      local lvl = ge.levels[n]
      for k, v in pairs(fields) do
        if k == 'cost' then lvl.cost = lvl.cost or {}; lvl.cost.Mana = v.Mana
        elseif v == false then lvl[k] = nil
        else lvl[k] = v end
      end
    end
    for set, ss in pairs(s.sets) do
      for k, v in pairs(ss.fields) do if v == false then set[k] = nil else set[k] = v end end
      for n, fields in pairs(ss.levels) do
        local lvl = set.levels[n]
        for k, v in pairs(fields) do if v == false then lvl[k] = nil else lvl[k] = v end end
      end
      if ss.constantStats then set.constantStats = ss.constantStats end
    end
  end
  saved = {}
  active = {}
end

local function remember(ge)
  if not saved[ge] then saved[ge] = { castTime = ge.castTime, levels = {}, sets = {} } end
  return saved[ge]
end

local function remember_set(s, set)
  if not s.sets[set] then
    local copy = {}
    for i, row in ipairs(set.constantStats or {}) do copy[i] = { row[1], row[2] } end
    s.sets[set] = { fields = {}, levels = {}, constantStats = set.constantStats and copy or nil }
  end
  return s.sets[set]
end

-- Guarda o valor original; `false` marca "nao existia" (o idioma `v == nil and false or v` devolve nil, nao false).
local function keep(table_, key, value)
  if table_[key] == nil then
    if value == nil then table_[key] = false else table_[key] = value end
  end
end

local function keep_level(s, n, key, value)
  s.levels[n] = s.levels[n] or {}
  if key == 'cost' then
    if s.levels[n].cost == nil then s.levels[n].cost = { Mana = value } end
  else
    keep(s.levels[n], key, value)
  end
end

local function sample_level(ge)
  local n = ge.levels[20] and 20 or #ge.levels
  return n, ge.levels[n] or {}
end

local function sample(ge)
  local n, lvl = sample_level(ge)
  local out = { castTime = ge.castTime, nivel = n }
  for k in pairs(LEVEL_FIELDS) do out[k] = lvl[k] end
  out.manaCost = lvl.cost and lvl.cost.Mana
  local sets = {}
  for i, set in ipairs(ge.statSets or {}) do
    local sl = set.levels and (set.levels[n] or set.levels[#set.levels]) or {}
    local row = { label = set.label, baseEffectiveness = set.baseEffectiveness, incrementalEffectiveness = set.incrementalEffectiveness }
    for k in pairs(LEVEL_FIELDS) do if sl[k] ~= nil then row[k] = sl[k] end end
    local stats = {}
    for j, stat in ipairs(set.stats or {}) do if finite(sl[j]) then stats[stat] = sl[j] end end
    row.stats = stats
    sets[i] = row
  end
  out.statSets = sets
  return out
end

local function chosen_sets(ge, gem)
  if gem.statSet then
    local set = (ge.statSets or {})[gem.statSet]
    assert(set, 'statSet ' .. tostring(gem.statSet) .. ' nao existe em ' .. ge.name)
    return { set }
  end
  return ge.statSets or {}
end

-- gem = { skill, set = {castTime, cooldown, critChance, baseMultiplier, storedUses, damageMultiplier, attackSpeedMultiplier,
--         attackTime, manaCost, spiritReservationFlat, baseEffectiveness, incrementalEffectiveness},
--         scale = {stat = fator}, constant = {stat = valor}, statSet = indice opcional }
local function apply_gem(gem)
  local ge = find_effect(gem.skill)
  assert(ge, 'Gem nao encontrada no PoB: ' .. tostring(gem.skill))
  local before = sample(ge)
  local s = remember(ge)
  local set = gem.set or {}
  for k, v in pairs(set) do
    assert(finite(v), k .. ' invalido')
    if k == 'castTime' then
      assert(v > 0, 'castTime invalido')
      ge.castTime = v
    elseif LEVEL_FIELDS[k] then
      for n, lvl in pairs(ge.levels) do keep_level(s, n, k, lvl[k]); lvl[k] = v end
      -- O nivel do statSet sobrepoe o do grantedEffect: onde o campo existir la, troca tambem.
      for _, ss in ipairs(ge.statSets or {}) do
        for n, lvl in pairs(ss.levels or {}) do
          if lvl[k] ~= nil then local r = remember_set(s, ss); r.levels[n] = r.levels[n] or {}; keep(r.levels[n], k, lvl[k]); lvl[k] = v end
        end
      end
    elseif k == 'manaCost' then
      for n, lvl in pairs(ge.levels) do
        keep_level(s, n, 'cost', lvl.cost and lvl.cost.Mana); lvl.cost = lvl.cost or {}; lvl.cost.Mana = v
      end
    elseif SET_FIELDS[k] then
      for _, ss in ipairs(chosen_sets(ge, gem)) do
        local r = remember_set(s, ss); keep(r.fields, k, ss[k]); ss[k] = v
      end
    else
      error('campo desconhecido: ' .. tostring(k))
    end
  end
  local scaled = {}
  for stat, factor in pairs(gem.scale or {}) do
    assert(finite(factor), 'fator invalido para ' .. stat)
    local found = false
    for _, ss in ipairs(chosen_sets(ge, gem)) do
      local index
      for i, name in ipairs(ss.stats or {}) do if name == stat then index = i end end
      if index then
        found = true
        local r = remember_set(s, ss)
        for n, lvl in pairs(ss.levels or {}) do
          if finite(lvl[index]) then r.levels[n] = r.levels[n] or {}; keep(r.levels[n], index, lvl[index]); lvl[index] = lvl[index] * factor end
        end
      end
    end
    assert(found, stat .. ' nao e stat por nivel de ' .. ge.name .. ' (use constant para stats fixos)')
    scaled[#scaled + 1] = stat
  end
  local constants = {}
  for stat, value in pairs(gem.constant or {}) do
    assert(finite(value), 'valor invalido para ' .. stat)
    for _, ss in ipairs(chosen_sets(ge, gem)) do
      remember_set(s, ss)
      local copy, found = {}, false
      for i, row in ipairs(ss.constantStats or {}) do
        copy[i] = { row[1], row[2] }
        if row[1] == stat then copy[i][2] = value; found = true end
      end
      if not found then copy[#copy + 1] = { stat, value } end
      ss.constantStats = copy
    end
    constants[#constants + 1] = stat
  end
  return { skill = gem.skill, pob = ge.name, id = ge.id, antes = before, depois = sample(ge), escalados = scaled, constantes = constants }
end

local function rebuild()
  if wipeGlobalCache then wipeGlobalCache() end
  if build and build.calcsTab then
    build.buildFlag = true
    build.calcsTab:BuildOutput()
  end
end

function M.apply(params)
  restore_all()
  local report = {}
  local ok, err = pcall(function()
    for _, gem in ipairs(params.gems or {}) do report[#report + 1] = apply_gem(gem) end
  end)
  if not ok then restore_all(); rebuild(); error(err) end
  active = report
  rebuild()
  return { protocol = PROTOCOL, gems = report }
end

-- Quais linhas de mod o parser do PoB entende; as que nao entende seriam descartadas caladas pela config.
function M.parse(params)
  local rows = {}
  for _, line in ipairs(params.lines or {}) do
    local mods, extra = modLib.parseMod(line)
    rows[#rows + 1] = { line = line, ok = (mods ~= nil and #mods > 0 and not extra), extra = extra }
  end
  return { protocol = PROTOCOL, rows = rows }
end

-- status {skill?}: relatorio da ultima aplicacao; com skill, a amostra atual da gem (nivel 20 ou o ultimo) na memoria do PoB.
function M.status(params)
  local out = { protocol = PROTOCOL, gems = active }
  if params.skill then
    local ge = find_effect(params.skill)
    assert(ge, 'Gem nao encontrada no PoB: ' .. tostring(params.skill))
    out.amostra = sample(ge)
    local n = tonumber(params.level)
    if n and ge.levels[n] then
      local row = {}
      for k, v in pairs(ge.levels[n]) do if type(v) ~= 'table' then row[tostring(k)] = v end end
      out.nivel = row
    end
  end
  return out
end

function M.install(handlers)
  local function wrap(fn) return function(params) local ok, r = pcall(fn, params or {}); if not ok then return { ok = false, error = tostring(r) } end; return { ok = true, result = r } end end
  handlers.sf_hypothesis_apply = wrap(M.apply); handlers.sf_hypothesis_parse = wrap(M.parse); handlers.sf_hypothesis_status = wrap(M.status)
end
return M
