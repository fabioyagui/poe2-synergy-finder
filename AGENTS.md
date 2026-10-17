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
Edges are rule-based guesses over game text, not confirmed mechanics or a power score. Quote the exact text and mark unconfirmed interactions [VERIFY]. Uniques and item mods are not in the map yet.

## Lab: build and measure in PoB (MCP `lab` tool, or Python)
The Finder's current build is read-only for the agent. To build something new, open a lab session: a second PoB engine, separate from the user's build.
- MCP: `lab open {from:"new", class:"Monk", level:14, weapon:"Gothic Quarterstaff"}` -> `lab add_skill {gems:[["Falling Thunder",5]]}` -> `lab config {values:{usePowerCharges:true}}` -> `lab select {group:1, part:2}` -> `lab stats {}` -> `lab export {name:"...", to_pob:true}` -> `lab close {}`. `tree_search` and `gear_search` take `metrics` (which group/part/field to read) and `weights`; keep budgets small (tree <= 22 points) because every candidate is a PoB calculation.
- Python (Claude Code in this folder): `from src.lab import Lab, bench, tree, gear, data`; `bench.verify_anchor(lab, "Quarterstaff", "Falling Thunder", 14)`, `bench.benchmark(lab, [14], ["Mace"])`, `tree.greedy_tree(...)`, `gear.search_gear(...)`. Always `lab.close()` (or `with Lab() as lab:`).
- Every lab number comes with its conditions (white weapon, no supports, enemy level, charges). Say them. "0" from PoB can mean "not modelled": check the skill text before concluding it has no effect.
- Save what you measure: `lab export` writes XML, PoB import code and the action log to `builds-teste/`; put conclusions in `docs/` with the date.

## Recommendation style
State which facts came from PoB calculations versus RePoE mechanical evidence. Prefer a few tested candidates with explicit tradeoffs over broad unvalidated advice.

# Instruções do PoE2 Synergy Finder

Quando a tarefa envolver descobrir, criar, comparar ou revisar builds de PoE 2,
leia `private/PROMPT-CRIADOR-DE-BUILDS-POE2.md` (arquivo local do autor, fora do repositório; se não existir, siga o método do `## Anchor discovery` acima).

Examine as ascendências antes de selecionar a build. Confirme as interações
na versão atual do jogo e diferencie dados confirmados de hipóteses.
