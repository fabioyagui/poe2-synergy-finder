@echo off
rem ASCII only in this file (no accents): cmd reads it in the OEM code page.
rem Opens Codex in this folder with the synergy-build-engine MCP enabled for this
rem session only (-c overrides). It does not change your Codex configuration; to
rem register it permanently use INSTALAR_CODEX_MCP.bat.
rem Keep the Finder open (START_POE2_SYNERGY_FINDER.bat) so the tools can reach it.
cd /d "%~dp0"
setlocal EnableExtensions EnableDelayedExpansion
title Codex - %~dp0

where codex >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Codex nao encontrado no PATH. Abra um novo terminal apos instalar.
    pause
    exit /b 1
)

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)"`) do set "PYEXE=%%P"
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)"`) do set "PYEXE=%%P"
)
if not defined PYEXE (
    echo [ERRO] Python nao encontrado.
    pause
    exit /b 1
)

set "SERVER=%~dp0mcp_server.py"
rem TOML literal strings (single quotes) keep Windows backslashes as they are.
set "C1=mcp_servers.synergy-build-engine.command='!PYEXE!'"
set "C2=mcp_servers.synergy-build-engine.args=['!SERVER!']"

if /i "%~1"=="--dry-run" (
    echo Pasta: %CD%
    echo Comando: codex -c "!C1!" -c "!C2!"
    exit /b 0
)

echo Pasta: %CD%
echo Abrindo Codex com o MCP synergy-build-engine desta pasta.
codex -c "!C1!" -c "!C2!" %*
if errorlevel 1 (
    echo.
    echo Codex saiu com erro ^(codigo !errorlevel!^).
    pause
)
endlocal
