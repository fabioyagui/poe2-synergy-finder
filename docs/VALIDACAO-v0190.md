# Validação — v0.19.0

## Resultado reproduzível neste pacote

A suíte completa passou após a integração de **Equipment & Market**, imagens de gear/gems e geração de buscas do PoE2 Trade.

```text
pytest -q
337 passed, 16 subtests passed in 3.53s
```

A mesma base também passou pelo discovery padrão do projeto:

```text
python -m unittest discover -s tests
Ran 337 tests in 2.992s
OK
```

Além disso:

- `node --check web/app.js` passou.
- `python -m py_compile app.py src/trade.py src/assets.py src/pob_bridge.py src/ggg_api.py` passou.
- Um smoke test do atualizador partindo de uma cópia v0.18.7 confirmou v0.19.0, presença de `src/trade.py`/`src/assets.py` e preservação de um arquivo sentinela em `data/`.
- O import usado por `test_tree_http_v16.py` foi ajustado para funcionar também com `pytest` a partir da raiz do projeto.

## O que a v0.19.0 valida

- parsing dos itens importados preserva as linhas candidatas a modifiers para o Market;
- normalização de texto e associação com IDs do catálogo de stats do trade2, incluindo ranges que o PoB renderiza como `+28(27-32)`;
- modifiers de um único valor podem sugerir `Min`; linhas com dois ou mais números não recebem limite automático;
- item Rare/Magic usa a base, sem tentar pesquisar o nome aleatório gerado;
- item Unique preserva o nome do Unique;
- payload de busca mantém filtros selecionados e sort por preço;
- resolução de arte converte o `dds_file` do índice RePoE para a URL de imagem esperada;
- endpoints locais `/api/assets/resolve`, `/api/trade/prepare` e `/api/trade/search` estão ligados ao app;
- CSP permite apenas os hosts de imagem externos necessários além de recursos locais;
- UI contém loadout, sockets de gems, tooltip, filtros Min/Max e ações de busca.

## Limites da validação

O ambiente usado para empacotar esta versão não possuía resolução DNS externa. Portanto, os testes não executaram uma busca real contra `pathofexile.com` nem baixaram o `base_items.min.json` do RePoE durante a validação final. O código de integração externa está coberto por testes locais com payloads controlados, mas a primeira execução em uma máquina com internet ainda deve confirmar:

1. download/cache do índice visual;
2. correspondência dos modifiers da build real com o catálogo atual do trade2;
3. criação e abertura de uma busca real na liga escolhida;
4. aparência das imagens reais dentro do loadout e dos sockets.

A falha de rede não bloqueia a leitura da build: quando uma arte não pode ser resolvida, a UI mostra um placeholder. A preparação dos filtros do Market precisa de acesso ao catálogo público do trade2.

## Segurança de dados

Esta feature não adiciona credenciais ao projeto. O catálogo de stats e o índice visual são caches locais sob `data/`, e a busca no Trade só é criada depois de ação explícita do usuário.
