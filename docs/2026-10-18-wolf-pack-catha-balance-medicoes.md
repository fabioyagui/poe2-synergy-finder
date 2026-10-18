# Wolf Pack + The Catha's Balance: lança, supports e tamanho da matilha (2026-10-18)

Continuação de `2026-10-18-lab-minion-catha-balance.md`. Todos os números são do PoB pelo lab do Finder:
Huntress/Spirit Walker nível 80, sem árvore normal, sem outro gear, inimigo padrão do lab para o nível.
"Lobo" = `TotalDPS` do minion, **um** lobo. Exports em `builds-teste/spiritwalker-wolfpack-*-l80.*`.

## Tamanho da matilha (texto da gem no PoB, não medido)

`skill_wolf_pack_size`: 3 lobos no nível 1, 5 no nível 18, 6 no nível 20; +0,05 por 1% de qualidade (20% = +1 lobo).
O PoB não multiplica o DPS pela matilha; a qualidade 20 não muda o número do lab. Total estimado = lobo × matilha,
assumindo que todos atacam o mesmo alvo [VERIFY no jogo].

## O nó liga a arma ao lobo

Sem The Catha's Balance o lobo fica em **37,0** com qualquer lança, branca ou rara. Com o nó (caminho da ascendência:
2x Shared Companion Damage, Wild Protector, Catha's Balance = 4 pontos), Wolf Pack 18, sem supports:

| Lança (Grand Spear, req 79) | Lobo | Degrau (gear.md) |
|---|---|---|
| branca | 64,7 | 1 |
| só +15% Attack Speed | 64,7 | — (velocidade local da arma não passa) |
| só Adds 32-54 Physical | 81,5 | 2 |
| só +169% increased Physical | 114,5 | 3 |
| +84% Physical | 88,5 | 2 |
| +84% Physical, Adds 18-32 | 108,5 | 2 |
| +169% Physical, Adds 32-54 (+15% atk spd não muda) | 171,4 | 3 |
| idem + Adds 20-40 Fire | 191,0 | 3 (fire local da arma também passa) |

Confirmado no PoB: passa o dano local da arma (físico e elemental, flat e %), não a velocidade.

## Supports que mudam o DPS do lobo (lança degrau 3, Catha alocado)

Testados um a um em cima de 64,7 (lança branca): Hulking Minions 88,1; Heavy Swing 96,3; Minion Mastery 76,4.
Sem efeito no PoB: Crazed Minions, Minion Pact I, Martial Tempo, Brutality, Ferocity, Feeding Frenzy, Primal Armament,
Rage, Ambush, Momentum, Ruthless, Overpower, Close Combat, Fist of War, Infernal Legion, Meat Shield, Elemental Army,
Last Gasp. "Sem efeito" pode ser "não modelado" (ex.: Crazed Minions, Feeding Frenzy são condicionais).

| Gems | Lobo | Matilha estimada |
|---|---|---|
| Wolf Pack 18 | 171,4 | ×5 = 857 |
| + Heavy Swing | 245,1 | ×5 = 1.226 |
| + Hulking Minions | 321,5 | ×5 = 1.608 |
| + Minion Mastery | 349,4 | ×5 = 1.747 |
| Wolf Pack **20** + os 3 | 414,5 | ×6 = 2.487 |

## Outros companions

- Tame Beast / Summon Beast: o PoB precisa da fera capturada escolhida na gem; o lab ainda não expõe essa escolha
  e o minion sai vazio. Pendente.
- Cackling Companions (hiena): 72,4 com lança branca + Catha.
- Rhoa Mount: 225,1 com lança branca + Catha. Chama atenção, mas é montaria (o jogador fica em cima); conferir
  se o PoB está aplicando o Catha a ela e como o ataque funciona no jogo [VERIFY].

## Pendências

1. Tame Beast com fera escolhida (expor `skillMinion` no lab).
2. Árvore normal: `tree_search` com `actor:"minion"` para ver quanto a árvore de Huntress adiciona.
3. Confirmar no jogo que os lobos recebem o dano da arma e que a matilha inteira ataca (o PoB mostra um lobo).
4. Rhoa Mount: entender o número antes de considerar.
