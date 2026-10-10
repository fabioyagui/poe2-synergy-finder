@echo off
setlocal EnableExtensions
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
set "MCPROOT=%LOCALAPPDATA%\PoE2 Synergy Finder\mcp"
if not defined LOCALAPPDATA set "MCPROOT=%USERPROFILE%\AppData\Local\PoE2 Synergy Finder\mcp"
if exist "%MCPROOT%\mcp_server.py" del /q "%MCPROOT%\mcp_server.py" >nul 2>nul
echo MCPs Synergy Finder removidos.
pause
