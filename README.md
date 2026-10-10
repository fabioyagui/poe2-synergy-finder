# PoE2 Synergy Finder v0.19.3

## Build visual + Market + Árvore + Cálculos

Nesta versão:

- **Equipment & Market**: a build importada agora mostra o equipamento em um loadout visual inspirado no jogo. Clique em uma peça para abrir o tooltip, revisar modifiers detectados, ajustar min/max e gerar uma busca no site oficial do PoE2 Trade. Há também uma busca somente pela base.
- **Gemas com arte**: grupos de skills mostram gemas e supports em sockets visuais. Quando a arte pode ser resolvida pelo índice RePoE, o Finder usa a imagem correspondente sem incluir arquivos de arte do jogo no ZIP.
- **Árvore visual**: posições e conexões obtidas do `PassiveSpec/PassiveTree` do seu PoB. Zoom, arrastar, minimapa, regiões, nós alocados, weapon sets, busca por nome/efeito/ID e marcadores por build.
- **Prévia no mapa**: clique num nó para ver o caminho de adição ou as dependências de remoção. O plano destaca os pontos que mudariam, sem gastar pontos nem alterar a build salva. A comparação usa o módulo de simulação da v0.16.
- **Sugestões por objetivo**: avaliação de até 12 caminhos próximos, com 1–5 pontos por caminho, usando `GetMiscCalculator` do PoB. Mostra total elegível, amostra avaliada, custo, ganho por ponto e diferenças. Não é uma busca exaustiva da melhor build e não confirma orçamento de pontos.
- **Cálculos**: escolha skill/efeito, modo de buffs e personagem/minion, quando o PoB expõe esse ator. Valores vêm de `calcsEnv.<actor>.output`; detalhes vêm de `breakdown`. Valores desconhecidos ficam pesquisáveis, métricas ausentes não viram zero.
- **Detalhamento**: fórmulas e tabelas retornadas pelo PoB; consultas de fontes de mods para campos selecionados. Um link `Tree:ID` abre o nó no mapa.
- **Importação direta**: `Carregar build` fecha a janela de importação e abre a Build atual. A biblioteca usa o mesmo fluxo; não há segunda confirmação obrigatória.

## Atualizar a instalação que já funciona

1. Pare o Motor PoB e feche o Finder.
2. Extraia este ZIP em uma pasta separada.
3. Execute `ATUALIZAR_INSTALACAO.bat` **na pasta nova**.
4. Selecione a instalação que você já usa, a pasta que contém `app.py`.
5. Abra o `START_POE2_SYNERGY_FINDER.bat` **da instalação atualizada**.

O atualizador aceita instalações da família v0.15 até v0.19.2. Faz backup do código e rollback se uma cópia falhar. Não copia, apaga ou substitui `data/` ou `engine/`; biblioteca, banco, build atual, configuração e PoB permanecem.

**Não precisa baixar PoB, bridge ou RePoE novamente.** Reinicie o motor após atualizar, porque a extensão local de árvore/cálculos é carregada na inicialização. A pasta pode manter o nome antigo; o cabeçalho deve mostrar v0.19.3.

Se você **moveu/renomeou a pasta inteira** e o diagnóstico perdeu caminhos absolutos, abra **Build atual → Motor PoB → Detectar / reparar caminhos**. A v0.19.2 relocaliza checkouts e também reconhece a instalação empacotada do PoB2; ela que vieram junto com a pasta e também procura de forma limitada em projetos próximos/Documentos. Se o checkout headless realmente não existir mais, use **Baixar PoB2 headless estável**; novos downloads ficam em `%LOCALAPPDATA%\PoE2 Synergy Finder\engine`, fora da pasta do projeto.

Também é possível abrir a versão nova separadamente, mas atualizar no lugar evita precisar selecionar/importar a build outra vez.

## Uso

Com seu XML/pobb.in já carregado, abra **Build atual**. A aba **Equipment & Market** funciona mesmo sem iniciar o Motor PoB; árvore e cálculos continuam exigindo o motor.

### Equipment & Market

Abra **Build atual → Equipment & Market** e clique em um slot equipado. O painel lateral mostra a peça e tenta relacionar as linhas de modifier ao catálogo público atual do PoE2 Trade.

- Cada modifier reconhecido pode ser ativado/desativado individualmente.
- `Min` e `Max` são editáveis antes da busca. Para uma linha com um único valor numérico, o Finder sugere esse valor como `Min`; linhas com vários números ficam sem limite automático para não adivinhar a semântica.
- `Buscar base` pesquisa somente a base do item.
- Em itens Rare/Magic, o nome gerado do item não é usado como filtro. Em Unique, o nome único é preservado.
- A busca só é enviada ao trade depois de um clique explícito; o resultado abre no site oficial.

As imagens são resolvidas em runtime a partir de metadados RePoE e servidas externamente. Se estiver offline ou uma arte não for encontrada, o texto e o Market continuam funcionando com um placeholder visual.

### Motor PoB

Para árvore e cálculos, vá a **Build atual → Motor PoB → Iniciar motor**.

### Árvore visual

Abra **Árvore visual**. A visão inicial enquadra os pontos da sua build.

- Arraste para mover, use a roda do mouse ou +/− para zoom. No canvas, setas movem e `/` foca a busca.
- `Centralizar build` enquadra suas alocações. `Visão geral` enquadra a região inteira.
- O seletor de região oferece árvore base, sua ascendência ou tudo.
- Pesquise `Area`, `Ignite`, `Life`, um nome de passiva ou ID. A busca também reconhece atalhos como `vida` e `área`.
- Selecione um resultado para localizar o nó. `Marcar local` salva até 12 marcadores no armazenamento local do navegador, por hash da build.
- Clique num ponto e confira o plano. `Comparar alteração no PoB` mostra diferenças sem modificar o XML.
- Sockets, escolhas especiais e operações de weapon sets não suportadas ficam somente para consulta.

A representação é **vetorial**, com círculos/arcos e identificadores de tipo. Usa a geometria do PoB, mas **não inclui texturas, ícones ou ilustrações do jogo**. Um nó sem coordenadas não recebe uma posição inventada.

### Sugestões

No painel lateral da árvore, abra **Sugestões**, escolha o objetivo e o limite de pontos, selecione a skill/efeito e clique em **Avaliar caminhos próximos**. Um filtro textual opcional restringe os nós a investigar.

A amostra é escolhida por menor custo de caminho e depois por ID. O ranking usa a mudança na métrica por ponto **apenas entre os caminhos avaliados**. A avaliação é normal-tree, não uma otimização de ascendências/atributos especiais. O controle A/A deve ser consistente; em caso de divergência, não é publicado um ranking.

O limite de pontos escolhido restringe o custo de cada caminho. Ele NÃO informa ao programa quantos pontos seu personagem realmente tem disponíveis.

### Cálculos

Abra **Cálculos** e escolha a skill/efeito. Esta aba lê a build importada, **não a prévia de adição/remoção do mapa**. As condições temporárias são usadas apenas na leitura e o XML é recarregado ao final.

As categorias mostram dano, DoT, área, ritmo/custos, recursos, defesa, resistências e atributos quando os campos existem. `Outros outputs do PoB` preserva os demais escalares. Clique em um valor para ver o detalhamento correspondente; há um seletor para consultar outras chaves de breakdown do motor.

`Fixar referência` guarda uma leitura em memória. A comparação só é exibida para o mesmo hash de build, skill, ator e modo. `Relatório JSON` exporta a leitura com contexto e fontes.

## Limites de precisão

- Nem toda mecânica ou interação está implementada no PoB. Presença de um valor não é validação de DPS ou uptime no jogo.
- As fontes de mods consultadas não são, isoladamente, uma fórmula completa de todos os resultados. Algumas métricas não têm detalhamento ou consulta de fontes nesta interface.
- O saldo de pontos, limites de ascendência e custo de respec não são verificados.
- Nenhuma alteração é aplicada permanentemente à build. Esta versão não é um editor completo de árvore com múltiplos planos acumulados.
- O diagnóstico anterior de troca de supports e a dependência de registro OAuth da GGG não foram resolvidos por esta entrega.

## Validação

Veja `docs/VALIDACAO-v0190.md`. Os testes exercitam módulos locais, parsing, endpoints HTTP e contratos da interface com dados sintéticos. **Não foi executada a instalação completa do PoB/Windows do usuário neste ambiente.** Resultados de fixtures não demonstram números reais do seu personagem.

## Fontes técnicas

- PoB PassiveTree: https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/PassiveTree.lua
- PoB PassiveSpec: https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/PassiveSpec.lua
- PoB CalcsTab: https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/CalcsTab.lua
- PoB CalcBreakdownControl: https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/CalcBreakdownControl.lua
- RePoE PoE2 export: https://repoe-fork.github.io/poe2/
- PoE2 Trade: https://www.pathofexile.com/trade2/search/poe2/Standard
- ggpk.exposed asset serving: https://ggpk.exposed/

Os arquivos do PoB e do bridge original não são redistribuídos neste ZIP nem modificados por essas extensões: o Finder cria sua cópia de trabalho do bridge. Dados do jogo e artes pertencem à Grinding Gear Games. Este programa não é afiliado à GGG, ao PoB ou ao poe.ninja.


## v0.18 — Codex MCP local

O Finder agora inclui `mcp_server.py`, um servidor MCP stdio sem dependências
externas. Ele atua como proxy compacto para o Finder já aberto em localhost.

Ferramentas:
- get_current_build
- get_calcs
- search_passives
- suggest_tree_paths
- preview_tree_change
- compare_tree_change
- search_catalog
- search_synergies
- inspect_entity

`INSTALAR_CODEX_MCP.bat` registra o servidor usando `codex mcp add`.
`TESTAR_CODEX_MCP.bat` testa localhost sem chamar modelo/API.

O servidor MCP não lê a internet e não guarda OpenAI API key. PoB e RePoE fazem
o trabalho pesado localmente; os resultados enviados ao Codex são compactados.


## v0.18.1 — MCP atual + Codex 0.154

Hotfix para `MCP client for synergy-finder timed out after 30 seconds`.

O servidor implementa:
- lifecycle moderno `server/discover` do MCP 2026-07-28;
- suporte anunciado para 2026-07-28, 2025-11-25 e revisões legadas usadas pelo projeto;
- lifecycle legado `initialize` / `notifications/initialized`;
- `tools/list` nos dois modos;
- `resources/templates/list` vazio para clientes que sondam catálogos opcionais.

O instalador registra o caminho absoluto do `python.exe`, não `py`, evitando
diferenças de PATH no subprocesso iniciado pelo Codex.

`TESTAR_HANDSHAKE_MCP.bat` valida discovery + tools/list moderno e
initialize + tools/list legado sem chamar modelo/API.


## v0.18.2 — catálogo de tools MCP 2026-07-28

Corrige o estado do Codex `/mcp`:

`synergy-finder: unknown (0 tools)`

O processo e o discovery já funcionavam na v0.18.1, porém o catálogo usava a
forma legada `{ tools: [...] }`.

No MCP 2026-07-28:
- `tools/list` agora retorna `resultType: "complete"`, `tools`, `ttlMs` e `cacheScope`;
- `tools/call` retorna `resultType: "complete"` e `isError`;
- as mesmas respostas continuam compatíveis com clientes legacy.

Nenhum arquivo do PoB é alterado.


## v0.18.3 — compatibilidade exata com Codex CLI 0.154.0

Corrige a suposição incorreta das versões 0.18.1/0.18.2 sobre MCP 2026.

O Codex CLI 0.154.0 envia `initialize` com `protocolVersion: 2025-06-18`.
Esta versão segue exatamente o lifecycle e os resultados da especificação
MCP 2025-06-18:

- `initialize` → `protocolVersion`, `capabilities.tools`, `serverInfo`;
- `notifications/initialized`;
- `tools/list` → `{ "tools": [...] }`;
- `tools/call` → `content` + `isError`, sem `resultType`.

Foi adicionado `data/mcp/handshake.log`, que registra apenas mensagens
JSON-RPC MCP locais (não prompts do Codex nem tokens OpenAI). Assim qualquer
incompatibilidade futura pode ser diagnosticada pelo tráfego real.


## v0.18.4 — schemas compatíveis com Codex 0.154

O diagnóstico de 1 tool provou que o transporte/handshake MCP funciona.
A versão completa agora expõe schemas deliberadamente simples ao Codex:
`type`, `properties`, `items`, `required` e descrições.

Keywords de validação que podem falhar no conversor interno do Codex 0.154
(`enum`, `default`, `minimum`, `maximum`, `maxItems`, `maxLength`,
`additionalProperties`) não são mais enviados no catálogo MCP.

As mesmas validações permanecem no servidor Python local, portanto a
semântica das ferramentas não foi relaxada.


## v0.18.5 — Codex 0.154 compatibility mode

O teste real no Codex confirmou que cada uma das 9 tools funciona quando exposta
por um MCP separado. O instalador padrão agora registra 9 servidores `synergy-*`,
cada um com exatamente uma tool, todos apontando para o mesmo Finder local.

O Finder, PoB e RePoE continuam únicos; apenas a exposição MCP foi separada.


## v0.18.6 — updater hotfix

Corrige a v0.18.5 que podia atualizar a interface sem substituir `mcp_server.py` e sem copiar `TESTAR_9_MCP_REAIS.*`. O updater agora gerencia explicitamente esses arquivos.


## v0.19.1 — portable paths + gem artwork repair

- caminhos absolutos do Motor PoB são reparados quando a pasta do Finder é movida/renomeada;
- “Detectar” também faz uma busca limitada por checkouts `PathOfBuilding-PoE2` próximos/Documentos;
- novos downloads headless ficam em `%LOCALAPPDATA%\PoE2 Synergy Finder\engine` no Windows, evitando nova quebra ao mover o projeto;
- ícones de gems usam `skill_gems.min.json` + `icon_dds_file`, não apenas `base_items`;
- imagens quebradas tentam a arte RePoE como fallback e depois viram placeholder limpo em vez do ícone quebrado do navegador.

## v0.19.0 — equipment visuals + PoE2 Trade links

- A aba **Equipamentos** virou um loadout visual inspirado no inventário in-game.
- Gear e gems tentam resolver arte pelo `base_items.min.json` do RePoE; a arte é servida pelo ggpk.exposed e não é incluída no repositório.
- Clicar em um equipamento abre um tooltip visual e cruza as linhas de modifier com o catálogo público atual de stats do `trade2`.
- **Buscar no Trade** cria a consulta somente após clique explícito, usando a base do item + filtros selecionados. Nomes aleatórios de itens Rare não são usados; Uniques preservam o nome exato.
- Min/max podem ser ajustados antes da busca e existe uma opção **Buscar somente a base**.
- O catálogo de stats do trade2 é cacheado localmente por 24 horas. Nenhuma credencial do usuário é armazenada para esta função.

## v0.18.7 — build lifecycle + single Finder instance

- Excluir a build ativa agora também limpa `data/pob/current.*` e encerra o motor PoB para não deixar cálculos de uma build removida.
- Builds apagadas ficam registradas em tombstones locais e não são recriadas pela migração automática de versões antigas. Reimportar manualmente a mesma build continua permitido.
- O MCP não escolhe silenciosamente a primeira instância quando há vários Finders abertos; ele retorna um erro explícito para evitar analisar uma build antiga.
- O app não abre silenciosamente em 8778/8779 quando outra instância já ocupa a porta padrão. Feche a janela antiga antes de iniciar uma nova versão.
- O reparo UTF-8 do MCP está incorporado no servidor desta versão.


## v0.19.3 — MCP portátil após mover a pasta

- O Codex agora usa um único servidor `synergy-build-engine` com as 9 tools.
- `INSTALAR_CODEX_MCP.bat`/`REPARAR_CODEX_MCP.bat` removem os registros antigos `synergy-*` que guardavam o caminho absoluto da pasta anterior.
- O `mcp_server.py` é copiado para `%LOCALAPPDATA%\PoE2 Synergy Finder\mcp`, então mover ou renomear a pasta do Finder não quebra mais o MCP.
- Depois de reparar, `/mcp` deve mostrar apenas `synergy-build-engine: connected (9 tools)` para o Finder.

## v0.19.2 — detecção do PoB instalado no Windows

- Corrige a detecção da instalação empacotada do PoB2 em `%APPDATA%\\Path of Building Community (PoE2)`, onde `Launch.lua`, `Modules`, `lua/xml.lua` e DLLs podem ficar no mesmo diretório.
- O campo manual **PoB2 / programa ou src** aceita tanto o diretório instalado quanto `PathOfBuilding-PoE2\\src` de um checkout.
- O motor agora monta `LUA_PATH` e `LUA_CPATH` a partir do runtime realmente detectado/configurado, sem assumir sempre `src\\..\\runtime`.
- `Detectar / reparar caminhos` tenta primeiro reutilizar o Runtime já encontrado como possível diretório do programa PoB2 antes de procurar outros checkouts.
