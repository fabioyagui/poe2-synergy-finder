# Lab: saída de minion e allocate com caminho (2026-10-18)

Commit `c9886a3`. Mudanças em `src/lab/engine.py`, `src/lab/service.py`, `src/lua/synergy_tree.lua`,
`mcp_server.py`, `AGENTS.md` e testes.

## O que mudou

- As respostas do lab (`stats`, `add_skill`, `equip`, `config`, `allocate`, `select`, `status`) trazem o bloco
  `minion: {...}` quando a skill selecionada tem minion ou companion. A fonte é `mainOutput.Minion` do PoB, a mesma
  saída da aba Calcs para minions. É o DPS de **um** minion; o PoB não expõe aqui quantos lobos o Wolf Pack mantém
  (`ActiveMinionLimit` vem 0).
- As métricas de `tree_search` e `gear_search` aceitam `actor: "minion"`.
- `allocate {add:[id]}` aloca também o caminho até o nó (sockets de joia vazios no caminho contam um ponto cada).
  `path: false` põe só o nó.

## Por que `allocate` de um nó isolado não mudava nada

O PoB poda nós sem ligação com o início da classe ou da ascendência (`PassiveSpec:BuildAllDependsAndPaths`).
O nó nem ficava alocado, mas a resposta antiga dizia `added`. Agora os nós podados voltam em `dropped`.
No caso testado (Fortified Aegis, nó 23940, Warrior 70), o caminho tem 22 pontos e passa por um Jewel Socket;
além disso o nó só afeta defesas do escudo equipado, então sem escudo as stats não mudam mesmo alocado.

Corrigido de quebra: o `allocate` antigo descartava os nós de ascendência já alocados a cada chamada.

## Medição: The Catha's Balance (nó 765, Spirit Walker) no Wolf Pack

Condições: Huntress/Spirit Walker nível 80, Wolf Pack gem 18 sem supports, arma branca, sem outro gear,
sem árvore normal, inimigo padrão do lab para o nível. Números do PoB (`TotalDPS` do minion, um lobo).

| Arma branca | Sem árvore | Caminho até 765 sem ele¹ | + The Catha's Balance | Ganho do nó |
|---|---|---|---|---|
| Hunting Spear | 37,0 | 45,0 | 48,0 | +6,7% |
| Grand Spear (req 79, 56-84 físico) | 37,0 | 45,0 | 64,7 | +44% |

¹ O caminho da ascendência: 2x Shared Companion Damage (10% increased cada) e Wild Protector.

O ganho é proporcional ao dano local da arma principal (60% dele vira dano adicionado de ataque dos companions,
`GainMainHandDmgFromParent` em `CalcOffence.lua`). Confirmado no PoB; o efeito no jogo não foi testado.

Pendente: medir com lança rara (degrau 2 ou 3 do método de gear), com supports de minion, e confirmar quantos
lobos o Wolf Pack mantém para chegar ao total da matilha. Export da sessão em
`builds-teste/spiritwalker-catha-wolfpack-l80.*`.
