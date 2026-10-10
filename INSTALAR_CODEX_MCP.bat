@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo.
echo PoE2 Synergy Finder - instalar/reparar Codex MCP
echo =================================================
echo.
where codex >nul 2>nul
if errorlevel 1 (echo Codex nao encontrado no PATH.& pause& exit /b 1)
set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)"`) do set "PYEXE=%%P"
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)"`) do set "PYEXE=%%P"
)
if not defined PYEXE (echo Python nao encontrado.& pause& exit /b 1)

set "MCPROOT=%LOCALAPPDATA%\PoE2 Synergy Finder\mcp"
if not defined LOCALAPPDATA set "MCPROOT=%USERPROFILE%\AppData\Local\PoE2 Synergy Finder\mcp"
if not exist "!MCPROOT!" mkdir "!MCPROOT!"
if errorlevel 1 (echo Nao foi possivel criar !MCPROOT!.& pause& exit /b 1)
copy /y "%~dp0mcp_server.py" "!MCPROOT!\mcp_server.py" >nul
if errorlevel 1 (echo Nao foi possivel instalar o servidor MCP estavel.& pause& exit /b 1)

rem Remove todos os registros antigos. Eles guardavam caminhos absolutos da pasta do projeto.
for %%N in (
 synergy-finder
 synergy-build-engine
 synergy-build
 synergy-calcs
 synergy-passives
 synergy-tree-suggest
 synergy-tree-preview
 synergy-tree-compare
 synergy-catalog
 synergy-synergies
 synergy-inspect
 synergy-test-01-get_current_build
 synergy-test-02-get_calcs
 synergy-test-03-search_passives
 synergy-test-04-suggest_tree_paths
 synergy-test-05-preview_tree_change
 synergy-test-06-compare_tree_change
 synergy-test-07-search_catalog
 synergy-test-08-search_synergies
 synergy-test-09-inspect_entity
) do codex mcp remove %%N >nul 2>nul

rem Um unico servidor agora expoe as 9 tools. O caminho fica fora da pasta do projeto,
rem portanto mover/renomear o Finder nao quebra o Codex MCP novamente.
codex mcp add synergy-build-engine -- "!PYEXE!" "!MCPROOT!\mcp_server.py"
if errorlevel 1 (echo Falha ao registrar synergy-build-engine.& pause& exit /b 1)

echo.
echo MCP instalado em caminho estavel:
echo !MCPROOT!\mcp_server.py
echo.
echo Esperado no /mcp:
echo   synergy-build-engine: connected (9 tools)
echo.
echo As entradas antigas synergy-build, synergy-calcs, etc. foram removidas.
echo Feche COMPLETAMENTE o Codex e abra novamente antes de rodar /mcp.
pause
