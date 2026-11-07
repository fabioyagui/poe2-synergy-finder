# Porte do lab do PoE 1: campanha, gear por ato e etapas por troca de skill (2026-11-07)

Mudanças feitas no lab do PoE 1 entre 2026-11-05 e 2026-11-07, portadas para o lab do PoE 2 depois de conferir
cada mecânica nos dados do PoE 2. Nada foi copiado sem essa conferência.

## O que entrou

| Peça | Arquivo | No PoE 2 |
|---|---|---|
| Resistência só a partir dos mapas | `judge.METAS`, `judge_stage` | Meta 0 em todas as faixas abaixo de `MAPS_LEVEL` (65). Meta 0 nunca reprova, nem resistência negativa. O valor continua no veredito. |
| Gear da campanha por ato | `judge.CAMPAIGN_GEAR`, `judge.campaign_gear` | Ato 1: 3 peças com 1 afixo. Ato 2 (16): 5 peças com 1. Ato 3 (33): todas com 1. Ato 4 e Interlúdios (46): todas com 2. É uma escolha de método que dá para calibrar [VERIFY in game]. |
| Limite no `gear_search` | `gear.search_gear(..., trilha)`, `gear.cap_affixes`, `gear.over_budget` | Na trilha campanha, cada peça fica com os afixos de maior ganho medido até o limite. As peças além do limite voltam a base branca (`branca` no relatório). A ação `lab gear_search` repassa `trilha`. |
| Só o loadout ativo | `stages.active_only` | `merge_loadouts` e `open {from:'xml'}` (novo no PoE 2) ficam só com o Spec, o SkillSet, o ItemSet e o ConfigSet ativos e com os itens que eles usam. |
| Nível que libera cada gem | `stages.unlock_level`, `gem_plan` (`libera`) | Support: o nível de personagem do nível 1 da gem. Skill ativa: o nível em que a gem alcança o tier (a gema bruta precisa dele), por exemplo Wolf Pack tier 8 libera no L26. Aparece no `etapas.md` e nas Notes do loadouts. As Notes omitem grupo cuja skill ainda está presa. |
| Gems por nível | `stages.shift_gem_blocks`, `swap_notice`, `run` | `gems: {nível: grupos}`: cada bloco vale do seu nível em diante. Um bloco cuja skill principal ainda não libera sobe para o nível de liberação. Cada troca vira etapa própria (`etapa_na_troca`, padrão sim). A etapa avisa "troca de skill" ou "troca de gems". Um respec com `skills` desliga o plano por nível. |

## Penalidade de resistência por faixa (corrigida)

Antes, a penalidade subia nos níveis da tabela de atos do PoB (`QuestRewards.lua`: 12, 28, 44, 51). Esses são os
níveis das missões de ponto de passiva, não os do início de cada ato, e a penalidade subia cedo demais. Agora
`stages.RESIST_PENALTY` usa estas faixas:

| Nível (como nível de área) | Penalidade | Fonte |
|---|---|---|
| 1 | 0 | Ato 1 |
| 16 | −10 | Ato 2 começa na área 16 (`world_areas.json` do RePoE PoE 2) |
| 33 | −20 | Ato 3 começa na área 33 |
| 46 | −30 | Ato 4 começa na área 46 |
| 54 | −40 | Interlúdios, área 54–59 (wiki do PoE 2, "Maximum Resistances") |
| 60 | −50 | Interlúdios, área 60–64 |
| 65 | −60 | fim de jogo |

O PoB 2 0.23.1 oferece os mesmos valores na config (`ConfigOptions.lua`: Act 1 0% … Act 6 −50%, Endgame −60%), mas
não diz em que área cada um começa. O nível do personagem faz as vezes do nível da área [VERIFY in game]. O
pedaço da tabela que depende de tempo pode mudar com o patch. A conta dos pontos de passiva continua igual
(`QuestRewards.lua`).

## Etapas por missão (item 5 do porte): fonte para o PoE 2

No PoE 1 o `campaign.py` lê os dados do Exile Leveling (rota, missões, gems por classe). No PoE 2 não existe gem
de missão por classe: as gems vêm de drop e de Uncut Skill Gems, e a skill ativa espera o tier (já modelado em
`gem_plan`). O que dá para usar:

- `world_areas.json` do RePoE PoE 2 (já é a fonte do catálogo): ato, nível de área, cidade, waypoint, chefes e
  conexões de cada área. Basta para nomear marcos por área (fim de ato, chefe, cidade) com o nível estimado.
- `QuestRewards.lua` do PoB 2: missões com ponto de passiva e o nível de área delas. Os níveis do PoB 2 não
  batem todos com o RePoE (Keth 25 contra 21, Isle of Kin 51 contra 46). Conferir antes de usar.
- Rotas abertas da comunidade (não conferidas): Domistae `poe2-leveling`, ExileXP (dados de campanha em
  TypeScript), `poe-leveling-overlay` (MIT). Conferir a licença de cada uma antes de importar.

Decisão do autor (2026-11-07): no PoE 2 as etapas ficam por nível; não há `por_area`. Faltava um marco de missão
que liberasse gem, e o nível já cobre o tier da skill. Um bloco `{nível: grupos}` cria a etapa no nível da troca.
