# Validação 0.16.0

## Executado nesta entrega

- 252 testes Python/API aprovados.
- Nesse total, 15 testes executam o módulo Lua usando Lua 5.4 e um modelo sintético
  do contrato do PoB: caminhos, dependências, snapshots imutáveis, repetição, bloqueio
  de IDs/tipos especiais e aplicação dos overrides. Não são simulações reais de DPS.
- HTTP local real: carregar contexto, gerar plano, comparar, rejeitar pedidos antigos,
  negar origem externa e servir os novos arquivos de interface.
- Transações: recarregamento do XML original, parada do motor em falha de restauração,
  serialização, detecção de troca de build e tratamento de outputs ausentes.
- Atualizador: preservação de data/engine, backup e rollback em erro de cópia.
- 22 verificações de interface em harness Chromium offline, usando a API HTTP local
  por binding de teste e um motor sintético: navegação, seleção, caminho/dependência,
  comparação, tabela de valores estáveis, JSON, paginação, erro/recuperação, escape
  de texto e layout a 760 px. Nenhuma exceção JavaScript foi encontrada.
- Verificação de sintaxe JavaScript e Python.

## Limites da validação

O navegador deste ambiente não permite navegação de rede; HTML, CSS e scripts
foram fornecidos diretamente ao harness. A rede local da API foi exercitada pelo
cliente HTTP Python, não pela pilha de rede do Chromium.

O ambiente não possui a instalação LuaJIT/PoB Windows do usuário e não baixou um
snapshot completo de PoB. Portanto **não foi executado um teste fim a fim de cálculo
com o personagem real do usuário**. Os resultados sintéticos não comprovam DPS,
cooldown, área ou alocação válida no jogo.

O mecanismo de cálculo foi conferido no código primário do PoB. O programa mostra
separadamente repetibilidade numérica A/A, caminho/dependências e orçamento não
verificado. Isso evita apresentar uma comparação matemática como build validada.

O diagnóstico anterior de Magnified Area e a suspensão de registros OAuth não
foram corrigidos nem reclassificados nesta entrega.
