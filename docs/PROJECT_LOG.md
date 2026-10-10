# Registro de continuidade

## v0.8.0 — 12/09/2026

Objetivo mantido: descobrir interações entre categorias usando dados, não um
formulário de build nem uma whitelist de supports. Tags e cores de atributos
continuam. Flameblast + Oil Grenade + Ignite é caso de teste, não limite do projeto.

Implementado:
- importação da árvore Default e definições de ascendência;
- todas as entidades reconhecidas, inclusive stats ainda não interpretados;
- separação de passivas, notables, keystones, nós de ascendência e elementos de UI;
- metadados e hashes separados para fontes gems/árvore;
- traduções conservadoras de stats, com lacunas contadas;
- relações com ação, conceito, aspecto, alcance, condição e origem;
- busca entre categorias e cadeias de dois efeitos por conceito;
- filtro de ascendência, fontes e JSON consultáveis;
- importação completa atômica, ou árvore incremental sem apagar gems.

Não implementado:
- cálculo de melhor caminho/passive points ou árvore desenhada;
- cobertura semântica de todos os stats;
- avaliação de uptime, DPS/EHP, custos ou mercado;
- uniques ou geração automática de uma build completa;
- otimização de conjuntos de vários supports.

Próxima validação: usuário importar JSONs reais e a árvore; conferir diagnóstico
de cobertura e alguns exemplos de Ignite em Interações. Não inventar quantidades
de registros importados no PC do usuário. Não chamar cadeias candidatas de
"melhorias" sem prova mecânica/quantitativa.


## v0.9.0
- Import PoB2 from pobb.in/raw, XML, file or export code.
- Baseline PlayerStats are read from exported PoB XML.
- Optional local PoB engine connector: /health, /build/load/xml, /build/info, /calc, /skills.


## v0.10.0
- PoB build promoted from modal-only view to a full application page.
- Fixed PoB Items parsing: item definitions live under <Items>; active ItemSet references them by Slot/itemId.
- Added equipped gear view and item parser diagnostics.
- Added common ConfigSet preservation.
- Skill groups from imported PoB can open the matching skill directly in the RePoE Finder.


## v0.11.0
- Replaced provisional HTTP PoB engine assumption with direct stdio JSON bridge.
- Added Windows setup diagnostics for LuaJIT, PoB src, runtime DLLs and bridge.
- Added runtime bridge downloader; GPL bridge source is fetched from upstream, not bundled.
- Added EngineClient process lifecycle: start/ping/load XML/get stats/get skills/items/tree/config/build info/stop.


## v0.16.0
Tree simulator uses PoB node IDs, path/dependencies and read-only addNodes/removeNodes overrides. Includes A/A control, entire-operation lock, stale-build rejection and checked XML restoration. In-place updater preserves engine/data. 252 tests and 22 offline browser checks; live Windows PoB integration not run in this build environment.


## v0.17.0 — árvore visual e cálculos
- Geometria obtida do PoB com busca, zoom, minimapa e marcadores.
- Caminhos/diferencas destacados como previa, sem aplicar ao XML.
- Sugestoes limitadas a uma amostra de caminhos normais, com custo e A/A.
- Calcs output/breakdown por skill/efeito/ator/modo; fontes Tree:ID localizaveis no mapa.
- Importar/usar build fecha modal e limpa caches de visoes anteriores.
- Atualizador preserva data/engine. Nenhum download do PoB exigido.
- Validacao local com fixtures; PoB Windows real nao executado.
