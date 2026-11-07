# Camada pob-layer: árvore nova antes do PoB oficial (2026-11-07)

O PoB 2 não sai no dia do patch: na 0.5.5 a GGG publicou o export da árvore em 2026-09-04 e o PoB lançou a árvore
em 2026-09-10. A camada `pob-layer` gera a árvore nova a partir do export oficial da GGG e mantém as correções que o
PoB faz à mão. O PoB instalado e as camadas do Finder (bridge, `src/lua/synergy_*.lua`, hipótese) não mudam.

## Como funciona

| Etapa | Onde | O que faz |
|---|---|---|
| Fonte | `github.com/grindinggear/poe2-skilltree-export` | `data.json` e `assets/` de cada versão (o commit tem o nome da versão: `0.5.5`, `0.5.0 Preview 2`) |
| Export | `src/lua/synergy_layer_tree.lua export` | Roda o `Export/Scripts/passivetree_ggg.lua` do próprio PoB fora da interface, e separa em várias linhas os stats que vêm com `\n` |
| Delta | `... delta` | O que o PoB mudou à mão sobre o export da GGG na versão base (export GGG da base contra o `TreeData/<base>/tree.lua` instalado) |
| Reaplicar | `... apply` | Aplica o delta campo a campo onde o nó da GGG continua igual ao da base. Se a GGG mexeu no nó, fica o texto novo e o caso vai para `conflitos`. Nós que só o PoB tem entram inteiros, ligados aos vizinhos. |
| Camada | `<engine>/pob-layer/` | `TreeData/<versão>/{tree.lua,tree.json,imagens}`, `GameVersions.lua` (o do PoB mais as versões novas) e `manifest.json` com o relatório |
| Motor | `pob_engine` (bootstrap) | Um prelúdio Lua faz `io.open`/`loadfile` lerem primeiro da camada os caminhos `TreeData/` e `GameVersions.lua`. Sem versão na camada, não há prelúdio. |
| Python | `pob_layer.resolve`, `tree_importer.pob_tree_file` | O importador de texto dos nós também lê o `tree.json` da camada |

Campos que o delta ignora, por serem só desenho: `icon`, `activeEffectImage`, `inactiveIcon`, `activeIcon`,
`flavourText`, `group`, `orbit`, `orbitIndex`, `x`, `y`, `nodeOverlay`, `connections`. `out`/`in` também ficam de fora
do delta: as ligações vêm sempre da GGG, e o `compare` confere as ligações à parte.

## Uso

```
python -m src.pob_layer commits
python -m src.pob_layer tree --versao 1_0 --ref <commit 1.0> --base 0_5 --base-ref bd87e651
python -m src.pob_layer status
python -m src.pob_layer remove 1_0
```

`--base-ref` é o commit do export da GGG que corresponde à árvore instalada da base. Para o `TreeData/0_5` do PoB
0.23.1, é o `bd87e651` (0.5.5).

## Provas

1. **Regenerar a 0.5.5:** o export GGG 0.5.5 mais o delta da própria 0.5.5 é idêntico ao `TreeData/0_5` instalado
   em tudo que entra no cálculo (4.912 nós). O delta tem 910 nós: 875 receitas de anoint, 12 `applyToArmour`, 6
   `sinister`, 6 nós trocáveis da Abyssal Lich (com `options`), 6 textos e 8 nomes.
2. **Backtest de uma versão para a seguinte:** delta da 0.5.4 (export GGG `e773f6c7` contra a árvore do PoB no
   commit `93e7794e`) aplicado ao export GGG 0.5.5. O resultado é **idêntico** à árvore 0.5.5 lançada pelo PoB (commit
   `49e93925`): nós, ligações, stats e flags. Foram 5.826 campos aplicados, 0 conflitos, e os 2 nós do Ritualist que
   o export não traz foram inseridos.
3. **Motor real:** a mesma build (starter Spirit Walker L75) carregada com a árvore instalada `0_5` e com a da camada
   (versão de teste `0_6`) dá os mesmos números: vida, resistências, EHP, atributos e DPS do lobo. Build nova
   (`new_build`) nasce na versão da camada. A versão de teste foi removida depois.
4. `tests/test_pob_layer.py`: prelúdio, GameVersions, `resolve`, refs inválidos e delta/apply/compare numa árvore
   sintética (conflito quando a GGG muda o nó, nó inserido, ícone ignorado).

## O que fica de fora

- **Desenho das ascendências:** o script do PoB lê `Ascendancy.dat` (`distanceTree`) para posicionar o desenho.
  Sem os arquivos do jogo, usamos uma distância fixa. Não entra no cálculo.
- **Nó novo da 1.0:** não tem correção antiga nem receita de anoint. O texto vem como a GGG escreveu; se o
  `ModParser` do PoB não entender a frase, o nó não tem efeito no cálculo. Conferir na aba de cálculos ou com o juiz.
- **Classes e ascendências novas** (Duelist/Knight, Shadow/Assassin/Infiltrator): os nós entram na árvore, mas a
  mecânica nova (Squire, stealth) precisa de código no PoB.
- Dados do jogo: ver a fase 2 abaixo.

## Fase 2: dados do jogo a partir do cliente instalado (2026-11-07)

`python -m src.pob_layer data` regenera os `Data/*.lua` do PoB a partir dos arquivos do cliente e leva para
`<camada>/Data/` só os que ficaram diferentes do PoB instalado. `python -m src.pob_layer remove-data` desliga.

| Peça | Como |
|---|---|
| Cliente | `find_game_dir`: Steam (`Bundles2/_.index.bin`) ou cliente da GGG (`Content.ggpk`), o atualizado por último. Aqui o da GGG parou em julho e o Steam é de 2026-11-06. |
| Extrator | `bun_extract_file.exe` + `libbun.dll` + `libooz.dll` da release v0.2.4 de `github.com/zao/ooz` (a fonte do CONTRIBUTING.md do PoB), sha256 fixado em `BUN_SHA256`, em `<engine>/tools/bun-0.2.4/`. Só lê o cliente. |
| Executor | `src/lua/synergy_layer_data.lua` faz o papel do `Export/Main.lua` do PoB (que é uma janela): carrega `GGPKData`/`Dat64File`, dá aos scripts `dat()`, `getFile()` e `processTemplateFile()` e roda `DATA_SCRIPTS` numa **cópia** de `Classes/Data/Export/Modules/Assets` do PoB (`pob-layer-src/data-work/`). |
| Esquema | O `Export/spec.lua` vem do branch `dev` do PoB no GitHub (`--spec`). O do 0.23.1 estava atrás do cliente: `Mods` tinha 693 bytes por linha no cliente e 677 no spec, e o script `mods` quebrava. |
| Comparação | Ignora a diferença CRLF/LF (o checkout do PoB vem com CRLF). Arquivo que o LuaJIT não compila não vai para a camada (`descartados`). |
| Python | `src/lab/data.py` (`data_file`, `data_files`) e `stages.load_acts` leem da camada: o juiz usa o `ModItem.lua` e as bases regeneradas. |

Resultado no cliente de 2026-11-06 (liga Forbidden Rites, 218 `.datc64`):
- 18 de 19 scripts rodaram. `bossData` falhou (`bossData.lua:392`, provavelmente depende de dado que o script
  espera de outra fonte), e o `BossSkills.lua` que ele deixou pela metade foi descartado.
- 34 arquivos ficaram diferentes do PoB 0.23.1. Exemplos: textos de gems (Brambles, Herald of Thunder),
  `statOrder` renumerado em `ModItem.lua` (a GGG inseriu stats), bases novas (`Runeforged Warden Bow`), tags de
  monstros, `WorldAreas.lua` e descrições de stat corrigidas.
- Motor real: com esses 34 arquivos, a starter Spirit Walker L75 dá os mesmos números do PoB puro (vida, res., EHP,
  atributos, DPS de lobo e urso). O juiz roda e dá as mesmas reprovas.

Limites:
- **Esquema:** se a GGG mudar o formato de um `.dat` e o `spec.lua` do `dev` ainda não tiver acompanhado, o script
  daquele dado falha (fica em `scripts` com o erro) e o arquivo continua o do PoB instalado.
- **Templates de skill:** gems novas dependem dos templates `Export/Skills/*.txt` do PoB, onde a mecânica é escrita à
  mão. Uma gem nova da 1.0 sai com os números do cliente, mas sem o tratamento especial que o PoB ainda não
  escreveu.
- **Dia do patch:** é preciso o cliente atualizado (o Steam baixa no lançamento) e rodar `data` de novo.
