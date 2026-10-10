# Codex + PoE2 Synergy Finder (MCP)

O Finder expõe **9 ferramentas locais** ao Codex por um servidor MCP stdio. Nenhuma chave da OpenAI fica armazenada no Finder.

## v0.19.3 — instalação portátil

A partir da v0.19.3 o Codex usa **um único servidor**:

`synergy-build-engine` → 9 tools

O arquivo MCP é copiado para um caminho estável em:

`%LOCALAPPDATA%\PoE2 Synergy Finder\mcp\mcp_server.py`

Isso é intencional: o Codex registra caminhos absolutos. Nas versões anteriores, mover ou renomear a pasta do projeto deixava entradas como `synergy-build`, `synergy-calcs` e `synergy-passives` apontando para o local antigo.

## Instalar ou reparar

1. Feche completamente o Codex.
2. Execute `REPARAR_CODEX_MCP.bat` ou `INSTALAR_CODEX_MCP.bat`.
3. Abra `START_POE2_SYNERGY_FINDER.bat` e mantenha o Finder aberto.
4. Abra o Codex novamente e execute `/mcp`.

Esperado:

`synergy-build-engine: connected (9 tools)`

As entradas antigas `synergy-build`, `synergy-calcs`, `synergy-passives`, `synergy-tree-*`, `synergy-catalog`, `synergy-synergies` e `synergy-inspect` são removidas automaticamente.

## Testar sem usar modelo

- `TESTAR_HANDSHAKE_MCP.bat` valida o handshake MCP e os 9 schemas localmente.
- `TESTAR_CODEX_MCP.bat` verifica a conexão com o Finder em localhost.

## Tools

- `get_current_build`
- `get_calcs`
- `search_passives`
- `suggest_tree_paths`
- `preview_tree_change`
- `compare_tree_change`
- `search_catalog`
- `search_synergies`
- `inspect_entity`

As tools retornam dados compactos; o Finder e o PoB fazem o trabalho pesado localmente.
