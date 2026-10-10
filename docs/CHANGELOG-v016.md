# 0.16.0 — Simulador de pontos

- Nova aba `Build atual → Simular pontos`, separada do Virtual Linker de supports.
- Catálogo, alocações, caminhos e dependências extraídos de `build.spec.nodes`.
- Experimento isolado ou com caminho/dependentes informados pelo PoB.
- Seleção explícita de grupo e efeito ativo da skill usada na comparação.
- Comparação nativa por `GetMiscCalculator` com `addNodes` e `removeNodes`.
- Snapshots copiados antes de cada rodada; ausência de métrica não tratada como zero.
- Controle A/A, identificação da build, lock transacional e verificação de restauração.
- Relatório JSON com baseline, resultado, IDs alterados e metadados do cálculo.
- Alterações complexas em weapon sets, sockets, masteries e escolhas especiais bloqueadas.
- Atualizador local de 0.15.0 para 0.16.0 que não mexe em data/ nem engine/.
- Encerramento do app para o processo headless; filas de respostas renovadas a cada início.

## Referências técnicas consultadas

Código dos próprios projetos; não são garantia de versão idêntica à instalação do usuário.

```text
https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/CalcsTab.lua
https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Modules/Calcs.lua
https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/master/src/Classes/PassiveSpec.lua
https://github.com/zgrummons/pob2-mcp/blob/main/pob-api/API/BuildOps.lua
https://github.com/zgrummons/pob2-mcp/blob/main/pob-api/API/Handlers.lua
```

O código nativo de `CalcsTab` testa nós adicionados/removidos pelo mesmo formato
`override.addNodes[node] = true` / `override.removeNodes[node] = true`. O novo módulo
utiliza esse contrato, mas faz suas próprias checagens de escopo e proteção.
