# Validação — v0.19.4

A v0.19.4 corrige a falha de inicialização do Motor PoB observada quando o Finder está dentro do OneDrive e o diretório gerado `engine/pob-api-v0126/API` não pode ser removido (`PermissionError: [WinError 5] Access is denied`).

## Mudança principal

- O overlay gerado do bridge passa a ficar em `%LOCALAPPDATA%\PoE2 Synergy Finder\engine\pob-api-v0126`, fora da árvore sincronizada pelo OneDrive.
- Se esse diretório estiver temporariamente bloqueado, `_prepare_bridge_overlay` usa um sibling único para a inicialização atual em vez de abortar.
- O bridge de origem do projeto continua sendo apenas a fonte; os patches e extensões são aplicados somente à cópia privada.

## Evidência do erro corrigido

O log fornecido mostrou a falha em `shutil.rmtree(BRIDGE_OVERLAY_DIR)` ao remover `...\engine\pob-api-v0126\API`. O erro de conexão `WinError 10053` apareceu depois, quando o navegador/cliente encerrou a requisição, e não é a causa inicial do motor não subir.

## Checagens locais

- Teste de portabilidade confirma que `%LOCALAPPDATA%` gera diretório de engine fora do projeto.
- Teste de regressão simula `PermissionError/WinError 5` ao apagar o overlay e confirma fallback para uma cópia única.
- Suíte automatizada completa: 350 testes passaram.
