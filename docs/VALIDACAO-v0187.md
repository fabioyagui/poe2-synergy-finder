# Validação v0.18.7

- 328 testes unitários/integrados: OK.
- HTTP real: importar XML -> Build atual -> excluir -> `/api/pob/current` retorna `imported:false`: OK.
- Biblioteca após exclusão da build ativa: 0 registros no cenário de teste: OK.
- Tombstone impede que `sync_siblings` recrie uma build apagada: OK.
- Reimportação manual da mesma build remove o tombstone e volta a permitir o registro: OK.
- Segunda instância do Finder no mesmo intervalo local é recusada com mensagem explícita: OK.
- MCP single-tool `get_current_build` em pipe simulado CP932: initialize + tools/list + Unicode UTF-8 estrito: OK.
- `--self-test` reporta MCP 0.18.7 e somente a tool selecionada: OK.

Não foi executado um cliente Codex Windows real dentro deste ambiente.
