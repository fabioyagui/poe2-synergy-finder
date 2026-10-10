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
3. `economy_resource` on the anchor's resource with `verbs=["PRODUCES","UNLOCKS"]`: connectors. Prefer producers in different slots (skill, support, passive, ascendancy).
4. `economy_resource` with `verbs=["AMPLIFIES","LIMITS"]`: scaling and conflicts. `economy_lookup` for the full text of any piece.
5. Only then build it and validate with `get_calcs` / `compare_tree_change`.
Edges are rule-based guesses over game text, not confirmed mechanics or a power score. Quote the exact text and mark unconfirmed interactions [VERIFY]. Uniques and item mods are not in the map yet.

## Recommendation style
State which facts came from PoB calculations versus RePoE mechanical evidence. Prefer a few tested candidates with explicit tradeoffs over broad unvalidated advice.

# Instruções do PoE2 Synergy Finder

Quando a tarefa envolver descobrir, criar, comparar ou revisar builds de PoE 2,
leia PROMPT-CRIADOR-DE-BUILDS-POE2.md nesta pasta e siga seu processo.

Examine as ascendências antes de selecionar a build. Confirme as interações
na versão atual do jogo e diferencie dados confirmados de hipóteses.
