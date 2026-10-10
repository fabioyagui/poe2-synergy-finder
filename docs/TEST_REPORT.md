# Relatório de testes — v0.8.0

Executados no ambiente Linux/Python desta entrega. O runtime não teve acesso
externo por DNS; o navegador Chromium bloqueou navegação direta para localhost.

## Automatizados Python

116 testes passaram. O total inclui os 52 testes herdados da v0.7 e os novos
casos de árvore/ascendências, traduções, interpretação semântica, isolamento de
scope, condições, chance versus garantia, preservação dos dados, importação
transacional, reimportação, arquivos inválidos, versões e cadeias candidatas.

O fluxo de download de sete arquivos foi testado com transporte HTTP simulado:
JSONs de teste passam pelo downloader/importador real. Isso NÃO é teste de rede
com o RePoE ao vivo. Uma falha de importação da árvore foi usada para confirmar
que a transação não deixa as gems parcialmente substituídas.

Os dados são sintéticos, com nomes marcados [TEST], salvo três pequenos excertos
de nós reais vistos pela ferramenta de pesquisa para validar formato. Não são
carregados automaticamente no aplicativo. Um teste herdado usa 1.300 gems
sintéticas para verificar ausência de whitelist/limite de catálogo.

## Interface/HTTP

23 verificações passaram em Chromium headless por harness DOM offline com
chamadas à API HTTP local real: categorias, filtros, cores, stats/JSON de nós,
cinco grupos semânticos, cadeias e evidências, ausência de notas /100, diagnóstico,
controles de atualização e layout estreito sem rolagem horizontal.

HTML, CSS e JavaScript de produção foram carregados no harness. Apenas fetch foi
encaminhado pelo harness ao servidor real. Não se deve confundir isso com
navegação nativa no Windows, nem com teste do CSP em navegação direta.
Nenhum erro JavaScript foi registrado nessas verificações.

## Ainda não validado

- importação end-to-end do snapshot completo baixado ao vivo do RePoE;
- execução nativa Windows;
- todas as regras/handlers de tradução e todos os efeitos do jogo;
- custo de alocação da árvore, equipamento e compatibilidade de uma build inteira;
- benefício real de DPS/defesa ou uptime de qualquer cadeia candidata.

Os JSONs do usuário e o download da árvore no PC dele serão a próxima verificação
da cobertura real. O aplicativo reporta lacunas em vez de afirmar que todas as
interações existem ou que as candidatas são upgrades.
