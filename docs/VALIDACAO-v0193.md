# Validação — v0.19.3

A v0.19.3 corrige portabilidade do Codex MCP depois que a pasta do projeto é movida ou renomeada.

## Mudança principal

O Codex registra o executável e os argumentos MCP com caminhos absolutos. As entradas de compatibilidade `synergy-build`, `synergy-calcs`, `synergy-passives` etc. podiam continuar apontando para a pasta antiga. A v0.19.3 instala uma cópia independente do `mcp_server.py` em `%LOCALAPPDATA%\PoE2 Synergy Finder\mcp` e registra apenas `synergy-build-engine`, que expõe as 9 tools.

## Checagens locais

- Handshake MCP `initialize` + `tools/list` validado com 9 tools.
- Os nove modos `--tool` continuam válidos para diagnóstico interno.
- Testes automatizados verificam que o instalador usa o caminho estável, remove nomes legados e não recria os nove registros antigos.
- O atualizador aceita v0.19.2 e preserva `data/` e `engine/` como antes.
- Suíte local: 348 testes passaram.
