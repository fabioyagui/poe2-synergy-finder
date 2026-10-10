# Fontes e referência — v0.8.0

Consultadas em 12/09/2026. Os arquivos baixados na execução terão seus próprios
hashes, caminhos locais e versão registrada no manifesto.

- RePoE PoE2: https://repoe-fork.github.io/poe2/
- Árvore Default: https://repoe-fork.github.io/poe2/passive_skill_trees/Default.min.json
- Ascendências: https://repoe-fork.github.io/poe2/ascendancies.min.json
- Traduções passivas: https://repoe-fork.github.io/poe2/stat_translations/passive_skill_stat_descriptions.min.json
- Traduções gerais: https://repoe-fork.github.io/poe2/stat_translations/stat_descriptions.min.json
- Documentação estrutural das traduções: https://repoe-fork.github.io/data-formats/stat_translations.html
- Repositório e aviso de formatos sujeitos a mudanças: https://github.com/repoe-fork/repoe
- Compatibilidade mantida da v0.7, referência de expressão: https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/blob/dev/src/Modules/CalcTools.lua

## Campos observados em registros reais

A árvore expõe, entre outros campos, `name`, `hash`, `id`, `stats`,
`is_notable`, `is_keystone`, `is_icon_only`, `ascendancy` e `granted_skill`.
A definição de ascendência fornece o nome correspondente ao ID do nó. Ela não
substitui os próprios stats da árvore.

Exemplos observados no texto da exportação consultada: nó 34290 com
`base_ignite_effect_+%`, nó 34419 com `ascendancy: Witch1`, nó 34478 com stats
sobre companion/poison e duração. Excertos desses formatos estão em testes;
não compõem uma base jogável nem representam importação do snapshot inteiro.

A documentação de traduções fornece `ids`, `English`, `condition`, `format`,
`index_handlers` e `string`. O renderizador recusa handlers/formatos que não
implementa. Isso evita mostrar uma unidade ou magnitude inventada.

## Separação de evidências

O algoritmo semântico é código deste projeto, não uma afirmação da GGG ou do PoB.
Uma frase reconhecida por regex pode exigir contexto adicional. Cada relação
mostra sua origem: flag, stat exato ou texto. Não há inferência Fire -> Ignite,
DPS calculado ou validação de alocação implícita.

Não foi baixado o corpus completo no ambiente de criação: DNS/rede externos
estavam indisponíveis para o runtime. As páginas foram consultadas pelo navegador
de pesquisa. Os testes usam fixtures e alguns excertos, não a base ao vivo.
