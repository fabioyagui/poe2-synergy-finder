-- PoE2 Synergy Finder: árvore de passivas a partir do export oficial da GGG, antes do PoB novo sair.
-- Roda fora do motor (luajit solto, com o runtime do PoB no cpath). Comandos:
--   export  <pob_root> <work_root> <versão> [distância_asc]  roda Export/Scripts/passivetree_ggg.lua do próprio PoB;
--                                                            lê <work_root>/TreeData/{data.json,assets} e grava
--                                                            <work_root>/TreeData/<versão>/tree.lua
--   delta   <pob_root> <ggg_antigo.lua> <pob_antigo.lua> <saída.lua>
--                                                            o que o PoB mudou à mão sobre o export da GGG
--   apply   <pob_root> <ggg_novo.lua> <delta.lua> <saída.lua>
--                                                            reaplica o delta onde a GGG não mexeu no nó
--   compare <pob_root> <a.lua> <b.lua>                       resumo das diferenças de cálculo entre duas árvores
-- Cada comando imprime uma linha JSON com o relatório.
local cmd, pob = arg[1], arg[2]
package.path = pob.."/runtime/lua/?.lua;"..pob.."/runtime/lua/?/init.lua;"..pob.."/src/?.lua;"..package.path
package.cpath = pob.."/runtime/?.dll;"..package.cpath
launch = { devMode = false }
function printf(...) io.stderr:write(string.format(...), "\n") end
function ConPrintf(...) io.stderr:write(string.format(...), "\n") end
dofile(pob.."/src/Modules/Common.lua")
local json = require("dkjson")

-- Campos de desenho: não entram no cálculo e não vão para o delta.
-- Vale em qualquer profundidade (as opções dos nós de atributo também trazem ícone).
local VISUAL = { icon = true, activeEffectImage = true, inactiveIcon = true, activeIcon = true, flavourText = true,
  group = true, orbit = true, orbitIndex = true, out = true, ["in"] = true, x = true, y = true,
  nodeOverlay = true, connections = true }

local function emit(t) io.write(json.encode(t), "\n") end

-- Igualdade só no que entra no cálculo.
local function deep_equal(a, b)
  if type(a) ~= type(b) then return false end
  if type(a) ~= "table" then return a == b end
  for k, v in pairs(a) do if not VISUAL[k] and not deep_equal(v, b[k]) then return false end end
  for k in pairs(b) do if not VISUAL[k] and a[k] == nil then return false end end
  return true
end

-- O export da GGG traz linhas de stat com "\n" dentro; a árvore do PoB as separa. Nó sem stats vira lista vazia,
-- como no PoB.
local function normalize(tree)
  for _, node in pairs(tree.nodes) do
    node.stats = node.stats or {}
    if type(node.stats) == "table" then
      local out = {}
      for _, s in ipairs(node.stats) do
        for line in (s .. "\n"):gmatch("([^\n]*)\n") do if line ~= "" then out[#out + 1] = line end end
      end
      node.stats = out
    end
  end
  return tree
end

local function write_tree(path, t)
  local out = assert(io.open(path, "w"))
  out:write("return ")
  writeLuaTable(out, t, 1)
  out:close()
end

local function sorted_keys(t)
  local r = {}
  for k in pairs(t) do r[#r + 1] = k end
  table.sort(r, function(a, b) return tostring(a) < tostring(b) end)
  return r
end

if cmd == "export" then
  local work, version, distance = arg[3], arg[4], tonumber(arg[5]) or 1000
  function GetWorkDir() return work .. "/Export" end
  -- Ascendancy.dat só dá distanceTree, que posiciona o desenho da ascendência; sem os arquivos do jogo, distância fixa.
  function dat() return { GetRow = function() return { distanceTree = distance } end } end
  local src = assert(io.open(pob .. "/src/Export/Scripts/passivetree_ggg.lua", "r")):read("*a")
  local n
  src, n = src:gsub('local version = "[%w_]+"', 'local version = "' .. version .. '"', 1)
  assert(n == 1, "passivetree_ggg.lua mudou: não achei a linha da versão")
  assert(loadstring(src, "passivetree_ggg.lua"))()
  local file = work .. "/TreeData/" .. version .. "/tree.lua"
  local tree = normalize(dofile(file))
  write_tree(file, tree)
  local nodes = 0
  for _ in pairs(tree.nodes) do nodes = nodes + 1 end
  emit({ ok = true, arquivo = file, nos = nodes, classes = #tree.classes })

elseif cmd == "delta" then
  local ggg, pobt = normalize(dofile(arg[3])), dofile(arg[4])
  local delta, count = {}, 0
  for id, p in pairs(pobt.nodes) do
    local g = ggg.nodes[id]
    if g then
      local change = {}
      for _, k in ipairs(sorted_keys(p)) do
        if not VISUAL[k] and not deep_equal(p[k], g[k]) then change[k] = { ggg = g[k], pob = p[k] } end
      end
      for _, k in ipairs(sorted_keys(g)) do
        if not VISUAL[k] and p[k] == nil then change[k] = { ggg = g[k], pob = "__nil__" } end
      end
      if next(change) then delta[id] = change; count = count + 1 end
    else
      -- Nó que o PoB tem e o export da GGG não traz (ex.: dois nós do Ritualist na 0.5.5): vai inteiro.
      delta.__added = delta.__added or {}
      delta.__added[id] = p
    end
  end
  local added = 0
  for _ in pairs(delta.__added or {}) do added = added + 1 end
  write_tree(arg[5], delta)
  emit({ ok = true, nos = count, nos_so_pob = added, arquivo = arg[5] })

elseif cmd == "apply" then
  local tree, delta = dofile(arg[3]), dofile(arg[4])
  local applied, already, conflicts, missing, inserted = 0, 0, {}, {}, {}
  local added = delta.__added or {}
  delta.__added = nil
  for _, id in ipairs(sorted_keys(added)) do
    if not tree.nodes[id] then
      local node = added[id]
      tree.nodes[id] = node
      -- Liga de volta os vizinhos que existem e põe o nó no grupo dele, se o grupo ainda existir.
      for _, dir in ipairs({ { "out", "in" }, { "in", "out" } }) do
        for _, other in ipairs(node[dir[1]] or {}) do
          local o = tree.nodes[tonumber(other)] or tree.nodes[other]
          if o then
            o[dir[2]] = o[dir[2]] or {}
            local has = false
            for _, v in ipairs(o[dir[2]]) do if tostring(v) == tostring(id) then has = true end end
            if not has then table.insert(o[dir[2]], type(o[dir[2]][1]) == "number" and tonumber(id) or tostring(id)) end
          end
        end
      end
      local g = node.group and tree.groups[node.group]
      if g and g.nodes then
        local has = false
        for _, v in ipairs(g.nodes) do if tostring(v) == tostring(id) then has = true end end
        if not has then table.insert(g.nodes, type(g.nodes[1]) == "number" and tonumber(id) or tostring(id)) end
      end
      inserted[#inserted + 1] = { no = id, nome = node.name }
    end
  end
  for _, id in ipairs(sorted_keys(delta)) do
    local node = tree.nodes[id]
    if not node then
      missing[#missing + 1] = id
    else
      for _, k in ipairs(sorted_keys(delta[id])) do
        local d = delta[id][k]
        local want = d.pob ~= "__nil__" and d.pob or nil
        if deep_equal(node[k], want) then
          already = already + 1
        elseif deep_equal(node[k], d.ggg) then
          node[k] = want
          applied = applied + 1
        else
          -- A GGG mudou o nó: a correção antiga pode não valer mais. Fica o texto novo da GGG.
          conflicts[#conflicts + 1] = { no = id, nome = node.name, campo = k, ggg_novo = node[k], pob_antigo = want }
        end
      end
    end
  end
  write_tree(arg[5], tree)
  emit({ ok = true, aplicados = applied, ja_iguais = already, conflitos = conflicts, nos_sumidos = missing,
    nos_inseridos = inserted })

elseif cmd == "tojson" then
  -- tree.json ao lado do tree.lua, como no TreeData do PoB (o importador do Finder lê o texto dos nós dele).
  local tree = dofile(arg[3])
  local function string_keys(t)
    local r = {}
    for k, v in pairs(t) do r[tostring(k)] = v end
    return r
  end
  tree.nodes = string_keys(tree.nodes)
  tree.groups = string_keys(tree.groups)
  local out = assert(io.open(arg[4], "w"))
  out:write(json.encode(tree))
  out:close()
  emit({ ok = true, arquivo = arg[4] })

elseif cmd == "compare" then
  local a, b = dofile(arg[3]), dofile(arg[4])
  local only_a, only_b, fields = {}, {}, {}
  for id, n in pairs(a.nodes) do
    local m = b.nodes[id]
    if not m then only_a[#only_a + 1] = id else
      local keys = {}
      for k in pairs(n) do keys[k] = true end
      for k in pairs(m) do keys[k] = true end
      for k in pairs(keys) do
        if not VISUAL[k] and not deep_equal(n[k], m[k]) then
          fields[k] = fields[k] or { n = 0, exemplos = {} }
          fields[k].n = fields[k].n + 1
          if #fields[k].exemplos < 5 then fields[k].exemplos[#fields[k].exemplos + 1] = id end
        end
      end
      if not deep_equal(n.out, m.out) or not deep_equal(n["in"], m["in"]) then
        fields.ligacoes = fields.ligacoes or { n = 0, exemplos = {} }
        fields.ligacoes.n = fields.ligacoes.n + 1
      end
    end
  end
  for id in pairs(b.nodes) do if not a.nodes[id] then only_b[#only_b + 1] = id end end
  local classes_a, classes_b = {}, {}
  for _, c in ipairs(a.classes) do classes_a[c.name] = #(c.ascendancies or {}) end
  for _, c in ipairs(b.classes) do classes_b[c.name] = #(c.ascendancies or {}) end
  emit({ ok = true, so_a = only_a, so_b = only_b, campos = fields, classes_a = classes_a, classes_b = classes_b })

else
  io.stderr:write("comando desconhecido: ", tostring(cmd), "\n")
  os.exit(2)
end
