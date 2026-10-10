# Validação — v0.17.0

## O que foi executado

- **301 testes automatizados** de Python, API HTTP e Lua. Incluem 36 casos que executam nossos módulos Lua via Lua 5.4 com um modelo sintético do contrato do PoB; 21 desses casos são novos nesta versão.
- **30 verificações de interface** em Chromium, com HTML/CSS/JavaScript do pacote e requisições reais a um servidor HTTP local do Finder, respondidas por um motor sintético.
- `node --check` em `app.js`, `tree-sim.js` e `workbench.js`.
- Atualização de uma cópia completa da v0.16.1, verificando código/backup e preservação de sete arquivos-sentinela de build, biblioteca, banco, configuração, credencial fictícia e motor. O teste não usou dados reais do usuário.

## Casos cobertos

Geometria de nós e arcos, escala da árvore, falta de coordenadas sem layout inventado, seleção e caminho, nó especial bloqueado, busca/localização, arrastar/zoom/minimapa, marcadores, comparar/restaurar, amostra limitada de sugestões, controle A/A, métrica ausente distinta de zero, leitura de Calcs, ator/modo de buffs, detalhamento e fontes, link Tree:ID, proteção contra build desatualizada, respostas atrasadas, erro de motor visível, importação que fecha o diálogo e abre a build e layouts desktop/tablet.

## Como o navegador foi testado

A política de navegação do Chromium do ambiente bloqueia URLs. Não foi alterada. O harness injeta os arquivos locais da interface numa página offline e encaminha `fetch` para as rotas HTTP reais do Finder. O armazenamento do navegador no harness é um Map em memória. Portanto o teste verifica persistência de marcadores entre abas da aplicação, não entre reinicializações reais do navegador. As rotas locais verificam Origin/X-Local-App em testes HTTP separados.

## Limites da validação

**Não executamos o PoB completo, LuaJIT no Windows, a instalação do usuário nem cálculos reais do seu personagem neste ambiente.** O código de cálculo da nova integração foi confrontado com fontes primárias do PoB, mas os testes de execução usam fixtures controladas. Passar na suíte NÃO demonstra exatidão de DPS/uptime no jogo nem compatibilidade com todo commit do PoB.

Os testes de updater executam cópias de arquivos em Linux; o seletor de pastas e os arquivos .bat no Windows não foram executados aqui.

Não foram testados login OAuth real, coleta de builds remotas, texturas do jogo nem uma otimização exaustiva de pontos. O problema anterior de Magnified Area não é declarado resolvido nesta entrega.

## Relatórios

- `unit_test_output_v17.txt`
- `browser_report_v17.json`
- `update_report_v17.json`

As imagens geradas pelo harness usam dados fictícios; não são resultados reais de uma build.
