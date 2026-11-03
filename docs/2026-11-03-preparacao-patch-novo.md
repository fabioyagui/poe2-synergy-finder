# Preparação para patch novo (2026-11-03)

Objetivo: entender as notas de um patch antes de o PoB 2 e o RePoE novos saírem. Referência: o mesmo trabalho
no PoE 1 (hipótese de patch, texto de nós, diff do catálogo), portado conferindo cada mecânica no PoB 2, não
copiada. Três peças, uma por commit, cada uma testada no PoB 2 headless.

## 1. Hipótese de patch: `lab hypothesis`

`src/lab/hypothesis.py` + `src/lua/synergy_hypothesis.lua` (extensão instalada no overlay privado do bridge,
depois do SynergyWorkbench). Troca na memória do PoB 2 (`data.skills`) os números de uma gem e aplica linhas
de mod customizado em todo motor do lab (sessão, `verify_anchor`, juiz, etapas) até `{reset:true}`.

Onde o PoB 2 lê cada número (conferido em `Modules/CalcActiveSkill.lua`, `CalcOffence.lua`, `CalcTools.lua`):

| campo da hipótese | onde o PoB 2 lê |
|---|---|
| `castTime` | `grantedEffect.castTime` (CalcOffence: base cast time) |
| `cooldown`, `storedUses`, `critChance`, `baseMultiplier`, `attackSpeedMultiplier`, `damageMultiplier`, `attackTime` | `grantedEffect.levels[n]`; se `statSets[i].levels[n]` tiver o campo, ele sobrepõe (CalcActiveSkill 792-797) |
| `manaCost` | `levels[n].cost.Mana` (no PoB 2 Spirit não é custo: é `spiritReservationFlat`) |
| `spiritReservationFlat` | `levels[n].spiritReservationFlat` → `ExtraSpirit` |
| `baseEffectiveness`, `incrementalEffectiveness` | `statSets[i]` (dano base por `actorLevel`, CalcTools 165-169); só vale para stats com `statInterpolation` 3 |
| `scale {stat: fator}` | `statSets[i].levels[n][índice]`, índice de `statSets[i].stats` (ex.: `spell_minimum_base_lightning_damage`) |
| `constant {stat: valor}` | `statSets[i].constantStats` |

Diferenças do PoE 1: os stats por nível e os fixos moram em `statSets` (não em `levels`), uma gem pode ter
vários (`statSet` escolhe um; sem ele, todos), `damageEffectiveness` não existe como campo (o equivalente é
`baseEffectiveness` do statSet), e o custo é só Mana.

Prova no PoB 2 headless (Monk 14, Gothic Quarterstaff branca, Tempest Bell 5, inimigo 14):

| | TotalDPS | Speed | Cooldown | CritChance | ManaCost |
|---|---|---|---|---|---|
| PoB instalado | 3,943 | 1,68 | 0,528 | 4,32 | 24 |
| hipótese: cooldown 1 s, crit 20, custo 99, "20% more Damage" | 2,829 | 0,978 | 1,023 | 7,2 | 99 |
| reset | 3,943 | 1,68 | 0,528 | 4,32 | 24 |

O cooldown antigo capa a velocidade em 1/cooldown (PoB 2 CalcOffence 2868) e o DPS cai; o reset devolve o
número exato. Também medido: Falling Thunder `baseMultiplier` 1,0 e `castTime` 1,5 (DPS 6,31 → 3,15, reset
exato) e Spark `scale` 0,5 do dano base (DPS 10,51 → 5,45, reset exato). `baseEffectiveness` em Spark não muda
nada: o dano do Spark vem dos stats por nível, não do `actorLevel`; o PoB mostra o antes/depois de cada campo
no relatório para o agente ver o que entrou. Um bug encontrado no caminho: guardar "não existia" com o idioma
`v == nil and false or v` devolve nil e deixava o crit da hipótese na gem; agora é `false` explícito.

Mod que o parser do PoB (`modLib.parseMod`) não entende é recusado com a linha (a config o descartaria
calado). Todo resultado do lab sai com `hipotese` {nome, fonte, gems, mods, aviso}.

Teste: `tests/test_lab_hypothesis.py` (validação pura + prova no motor real).

## 2. Texto de nós que o RePoE deixa sem efeito

No PoE 1 o RePoE traduzia o stat de keystone para o próprio nome e nenhuma keystone entrava no mapa de
âncoras. No RePoE do PoE 2 (4.5.5.2) isso **não acontece**: as 33 keystones vêm com o texto do efeito. O que
falta são 79 stats sem tradução em 68 nós (36 de ascendência, 23 notáveis, 9 passivas), ex.:
`life_regeneration_rate_per_minute_%` ("Regenerate 0.2% of maximum Life per second"),
`life_remnants_gain_per_globe` (Sanguimancy: "Grants Skill: Life Remnants"), `max_jade_stacks` (Jade Heritage:
"Grants Skill: Encase in Jade"), `consume_all_owl_feathers_on_dodge` (The Mhacha's Gift).

`src/tree_importer.py` lê o texto dos nós em `TreeData/<última versão de GameVersions.lua>/tree.json` do PoB
instalado (hash do RePoE = `skill` do PoB; 4914 nós, 4496 com texto) e o acrescenta onde o RePoE não traduziu
ou só repete o nome, com `source: "pob_tree"`. Reimportada a árvore na base: **48 nós ganharam 60 linhas**
(21 de ascendência, 20 notáveis, 7 passivas); os outros 20 dos 68 só tinham stats `no_display` cujo texto o
RePoE já dava por outro stat. Teste: `tests/test_tree_pob_text.py`.

## 3. Diff do catálogo entre versões: `lab patch_diff`

`src/catalog_diff.py`. Compara a pasta do catálogo importado na base (`meta.import.folder`; se mudou de lugar,
o snapshot com o mesmo sha256 do `skill_gems.min.json`) com o snapshot baixado mais recente em
`data/raw/snapshots/`, ou duas pastas dadas (`antes`, `depois`). Arquivos e campos do RePoE do PoE 2:

- gems (`skill_gems.min.json`): tipo, tags, skills concedidas, tier de gema bruta, lineage, cor; e para cada
  skill concedida (`skills.min.json`): tempo de conjuração, tipos, restrições de arma, `static` (cooldown,
  usos, custos, reservas, multiplicadores), níveis 1 e máximo, tipos do support, cada `stat_set` (stats fixos,
  stats de qualidade, por nível nos níveis 1 e máximo, ex. `damage_multiplier`);
- skills sem gem (monstros, minions, disparadas): só contadas;
- árvore (`passive_skill_trees/Default.min.json`): nome, keystone, notável, soquete, ascendência, stats.

Relatório em `builds-teste/patch/<nome>.md` e `.json`. Validado com uma cópia do snapshot real com sete
mudanças plantadas (gem nova, removida, alterada em custo/cooldown/dano por nível, skill sem gem alterada, nó
novo, removido, alterado): o diff acha exatamente elas; a versão contra ela mesma dá zero
(`tests/test_catalog_diff.py`). Não diz se é buff ou nerf: isso é leitura, com o PoB medindo via hipótese.

## Cache de medições

O PoE 2 não tem cache de medições isoladas (o `verify_anchor` abre um motor por chamada). Não foi criado;
`hypothesis.stamp()` já existe para separar medidas com hipótese quando um cache aparecer, e a chave terá de
vir do catálogo importado na base, não de um manifest de pasta.

## O que fica de fora

- Skill, support, keystone, notável ou ascendência **nova** não é simulável por hipótese: não há como criar
  uma gem no PoB a partir das notas. Fica como "pendente de teste no jogo" até o PoB novo.
- Mudança de mecânica (um stat novo, uma regra de cálculo) idem: a hipótese só troca números que o PoB já lê.
- `baseEffectiveness` só pesa em stats por `actorLevel` (interpolação 3); dano fixo por nível usa `scale`.
- Nós sem stats no RePoE mas com "Grants Skill: X" no PoB (43) não ganharam texto: o `granted_skill` do
  RePoE já vira o link GRANTS_SKILL.
- Não há diff dos arquivos do PoB (Data/Skills): a versão anterior fica no histórico do repositório do PoB.

## Verificação

- Suíte: ver `docs/PROJECT_LOG.md` (entrada 2026-11-03).
- `TESTAR_HANDSHAKE_MCP.py`: contagem de tools atualizada para 17 (estava em 15 desde `economy_pairs` e
  `judge_build`, antes deste trabalho).
