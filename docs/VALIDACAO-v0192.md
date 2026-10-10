# Validação — v0.19.2

Correção focada na portabilidade do Motor PoB no Windows.

- Aceita checkout de desenvolvimento (`repo/src` + `repo/runtime/lua`).
- Aceita instalação empacotada/GUI (`Launch.lua`, `Modules` e `lua/xml.lua` no mesmo diretório).
- O runtime configurado passa a alimentar `LUA_PATH` e `LUA_CPATH`; o motor não presume mais que todo programa PoB está em `repo/src`.
- A detecção reaproveita o caminho de Runtime já válido como pista para localizar o programa PoB2.
- Testes de regressão incluem os layouts checkout e GUI.

Validação local: **344 testes Python passaram**; `node --check` passou em `web/app.js`, `web/workbench.js` e `web/tree-sim.js`.
