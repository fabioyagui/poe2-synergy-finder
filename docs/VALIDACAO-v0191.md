# Validação — v0.19.1

## Correções desta versão

- Reparo de caminhos absolutos do Motor PoB quando a pasta do Finder é movida ou renomeada.
- Detecção limitada de checkouts `PathOfBuilding-PoE2` em projetos próximos e pastas Documentos.
- Novos downloads headless no Windows usam `%LOCALAPPDATA%\PoE2 Synergy Finder\engine`, evitando dependência da localização do projeto.
- Gems agora usam `skill_gems.min.json` e `icon_dds_file` para resolver a arte real; `base_items.min.json` continua sendo usado para gear/armas.
- Imagem fornecida pela build que falhar tenta a arte resolvida pelo RePoE e, se ainda falhar, vira placeholder em vez de mostrar o ícone quebrado do navegador.

## Testes executados

```text
python -m unittest discover -s tests
Ran 340 tests
OK

pytest -q
340 passed, 16 subtests passed
```

Também passaram:

- `python -m py_compile app.py src/*.py atualizar_instalacao.py`;
- `node --check web/app.js`;
- smoke test do atualizador partindo de v0.19.0, preservando arquivos sentinela em `data/` e `engine/`.

## Cenários de portabilidade cobertos

1. configuração contém caminhos absolutos antigos para `engine/pob-api` e `engine/PathOfBuilding-PoE2/src`;
2. o projeto inteiro é movido e esses recursos continuam dentro da nova pasta;
3. o Finder rebasa automaticamente bridge, PoB source e runtime;
4. a ação Detectar pode localizar um checkout antigo em outra pasta próxima sem varrer o disco inteiro;
5. se for necessário baixar novamente, o checkout novo usa uma pasta estável no perfil do usuário no Windows.

## Limites

Os testes não executam o cliente PoE2 nem validam visualmente cada asset existente no jogo. O resolvedor usa metadados atuais do RePoE e `image.ggpk.exposed`; indisponibilidade de rede ou asset ausente mantém a build funcional e exibe fallback.
