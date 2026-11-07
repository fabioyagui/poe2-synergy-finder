# PoE2 Synergy Finder — Codex instructions

When the `synergy-finder` MCP server is available, use it for Path of Exile 2 build questions instead of reading large local JSON files.

## Source of truth
- PoB calculations are the numerical validator.
- RePoE is used for mechanical discovery/evidence, not a power score.
- Do not infer that tags prove synergy.
- Do not invent `/100` build scores.
- Tree suggestions are a bounded sample of nearby paths, not a global optimizer.
- `point_budget_verified=false` means the tool did not prove the character has those points available.
- Never claim that a missing PoB metric is zero.

## Token-efficient workflow
1. Call `get_current_build`.
2. Call `get_calcs` with only the metrics needed for the user's goal.
3. For passives, prefer `suggest_tree_paths` with a small limit (4–8).
4. Use `preview_tree_change` before `compare_tree_change` when only path/cost is needed.
5. Use `search_catalog` / `search_synergies` only for the mechanic being investigated.
6. Never request or dump the whole passive tree or raw RePoE corpus into context.

## Anchor discovery (resource economy)
Use this before picking a skill, when the question is "where is the power" rather than "tune this build".
1. `economy_status` once: method, verbs, resource list.
2. `economy_anchors`: effects that REPLICATE, READ or CONSUME a resource for "more" damage, or UNLOCK a cap/cost. `by_resource` shows where the most multipliers can stack.
3. `verify_anchor` on each candidate skill: PoB measures the real multiplier (charges, enemy states). Only `specific` rows confirm an anchor; `axis` tells damage from defence. Text anchors without a PoB number are hypotheses.
4. `economy_resource` on the anchor's resource with `verbs=["PRODUCES","UNLOCKS"]`: connectors. Prefer producers in different slots (skill, support, passive, ascendancy).
5. `economy_resource` with `verbs=["AMPLIFIES","LIMITS"]`: scaling and conflicts. `economy_lookup` for the full text of any piece.
6. Only then build it and validate with `get_calcs` / `compare_tree_change`.
Edges are rule-based guesses over game text, not confirmed mechanics or a power score. Quote the exact text and mark unconfirmed interactions [VERIFY]. Items from PoB are in the map: uniques, item mods, jewels (`kinds=["JEWELS"]`: JEWEL_MOD, TIME_LOST, JEWEL_UNIQUE, TIMELESS) and item augments (`kinds=["AUGMENTS"]`: RUNE, SOUL_CORE, IDOL); each row carries `degrau` (estimated acquisition tier), `radius` (a radius jewel's value depends on the nodes around the socket, never a fixed number) and `note` (Runes, Soul Cores and Idols share one item socket). Cluster jewels and the PoE1 Timeless legions have no 0.5 data and are not imported.

## Lab: build and measure in PoB (MCP `lab` tool, or Python)
The Finder's current build is read-only for the agent. To build something new, open a lab session: a second PoB engine, separate from the user's build.
- MCP: `lab open {from:"new", class:"Monk", level:14, weapon:"Gothic Quarterstaff"}` (or `{from:"xml", path|xml}` for an outside PoB export; only its active loadout is kept) -> `lab add_skill {gems:[["Falling Thunder",5]]}` -> `lab config {values:{usePowerCharges:true}}` -> `lab select {group:1, part:2}` -> `lab stats {}` -> `lab export {name:"...", to_pob:true}` -> `lab close {}`. `tree_search` and `gear_search` take `metrics` (which group/part/field to read) and `weights`; below the maps level `gear_search` is campaign gear (`judge.CAMPAIGN_GEAR`: affixed pieces and affixes per piece by act, the lowest-gain pieces go back to white bases; `trilha` only matters from level 65); keep budgets small (tree <= 22 points) because every candidate is a PoB calculation.
- Python (Claude Code in this folder): `from src.lab import Lab, bench, tree, gear, data`; `bench.verify_anchor(lab, "Quarterstaff", "Falling Thunder", 14)`, `bench.benchmark(lab, [14], ["Mace"])`, `tree.greedy_tree(...)`, `gear.search_gear(...)`. Always `lab.close()` (or `with Lab() as lab:`).
- Minion/companion skills (Wolf Pack, Tame Beast): lab responses add a `minion` block (PoB minion output, one minion, not the pack total); `tree_search`/`gear_search` metrics take `actor:"minion"`.
- `allocate {add:[id]}` also allocates the path to the node (empty jewel sockets on the way included). PoB prunes nodes with no link to the class/ascendancy start; with `path:false` those come back in `dropped` and do not count.
- Builds by level stage: `lab stages {levels?, gems?, respecs?, gear?, config?, name?, trilha?}` writes `builds-teste/<name>/L<level>.xml` per stage (tree cut to the level budget = level − 1 + quest points from the installed PoB `QuestRewards.lua`; ascendancy by ascension level in `judge.ASCENSIONS`; gem level allowed by the character level; an active skill waits until the gem level reaches its tier, e.g. Wolf Pack tier 8 from level 26; resistance penalty by area level in `stages.RESIST_PENALTY`: 0 / −10 from 16 / −20 from 33 / −30 from 46 / −40 from 54 / −50 from 60 / −60 from 65), `etapas.md`, one PoB loadouts file and `juiz.json`. Each gem shows the character level that unlocks it (active skill: the level where the uncut gem reaches its tier). `gems` may be `{level: groups}`: each block applies from its level on, a block whose main skill is still locked moves to the unlock level, and each swap becomes its own stage (`etapa_na_troca`, default true); the stage warns "troca de skill" or "troca de gems". The loadouts file and `open from xml` keep only the active loadout (Spec, SkillSet, ItemSet, ConfigSet and the items they use). The session keeps the allocation order (`allocate`, `tree_search`) to cut the tree per stage; groups granted by items or nodes stay as PoB builds them.
- Judge: `lab judge {path, trilha?}` or the `judge_build` tool rates a stage folder or one XML: legality (points, ascendancy, gem level and tier, attributes, item level, each mod within its tier on the base via `ModItem.lua`, rune sockets), track tiers (supports per skill 3/4/5, lineage supports, uniques and league or PoB-hidden bases only in `desbalanceada`), Spirit, mana, curses, resistance and life targets by band (resistance only from the maps level: a 0 target never fails), honest config. It warns about skills granted from the second weapon set. A stage folder needs `ancora.md` with a `Trilha:` line. Thresholds in `src/lab/judge.py` (`ASCENSIONS`, `METAS`, `CAMPAIGN_GEAR`, `MAX_SUPPORTS`) are method choices marked [VERIFY], not game data.
- Every lab number comes with its conditions (white weapon, no supports, enemy level, charges). Say them. "0" from PoB can mean "not modelled": check the skill text before concluding it has no effect.
- Save what you measure: `lab export` writes XML, PoB import code and the action log to `builds-teste/`; put conclusions in `docs/` with the date.

## Patch notes before the new PoB 2 / RePoE
- `lab hypothesis {nome?, fonte?, gems?:[{skill, set?, scale?, constant?, statSet?}], mods?:[...]}` changes gem numbers in the PoB 2 memory (`set`: castTime, cooldown, critChance, baseMultiplier, storedUses, damageMultiplier, attackSpeedMultiplier, attackTime, manaCost, spiritReservationFlat, baseEffectiveness, incrementalEffectiveness; `scale`: a per-level stat of the statSet, e.g. `spell_minimum_base_lightning_damage`; `constant`: a fixed stat) and applies custom mod lines to every lab engine until `lab hypothesis {reset:true}`. A mod the PoB parser does not understand is refused. Every result carries `hipotese`: it is an estimate from the notes, not the new PoB. Skill, support, keystone or ascendancy that does not exist yet cannot be simulated this way; say so.
- `lab patch_diff {antes?, depois?, name?}` after the new RePoE is downloaded: compares the catalog imported in the base with the latest snapshot (gems new/removed/changed, skills without a gem only counted, tree nodes) and writes `builds-teste/patch/<name>.md|.json`. It reports data changes, not buffs or nerfs; measure with PoB.
- Tree text: where RePoE leaves a node stat without translation, the importer reads the node text from the installed PoB `TreeData/<latest>/tree.json` (`source: "pob_tree"` in the entity texts). Keystones already come translated in the PoE 2 RePoE.

## Recommendation style
State which facts came from PoB calculations versus RePoE mechanical evidence. Prefer a few tested candidates with explicit tradeoffs over broad unvalidated advice.

# Instruções do PoE2 Synergy Finder

Quando a tarefa envolver descobrir, criar, comparar ou revisar builds de PoE 2,
leia `private/PROMPT-CRIADOR-DE-BUILDS-POE2.md` (arquivo local do autor, fora do repositório; se não existir, siga o método do `## Anchor discovery` acima).

Examine as ascendências antes de selecionar a build. Confirme as interações
na versão atual do jogo e diferencie dados confirmados de hipóteses.
