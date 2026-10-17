@echo off
rem ASCII only in this file (no accents): cmd reads it in the OEM code page.
rem Opens Claude Code in this folder. The .mcp.json and CLAUDE.md here register the
rem synergy-build-engine MCP (15 tools) and the AGENTS.md rules automatically.
rem Keep the Finder open (START_POE2_SYNERGY_FINDER.bat) so the tools can reach it.
cd /d "%~dp0"
setlocal
title Claude Code - %~dp0

set "CLAUDE_EXE="
where claude >nul 2>&1 && set "CLAUDE_EXE=claude"
if not defined CLAUDE_EXE if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE_EXE (
    echo [ERRO] Claude Code nao encontrado.
    echo Instale com:  winget install Anthropic.ClaudeCode
    echo ou no PowerShell:  irm https://claude.ai/install.ps1 ^| iex
    pause
    exit /b 1
)

if /i "%~1"=="--dry-run" (
    echo Pasta: %CD%
    echo Comando: "%CLAUDE_EXE%"
    exit /b 0
)

echo Pasta: %CD%
echo.
echo  [1] Nova sessao
echo  [2] Continuar a ultima sessao
echo  [3] Escolher uma sessao anterior
echo.
choice /c 123 /n /m "Opcao (1-3): "
if errorlevel 3 goto resume
if errorlevel 2 goto continue

:new
"%CLAUDE_EXE%" %*
goto end

:continue
"%CLAUDE_EXE%" --continue %*
goto end

:resume
"%CLAUDE_EXE%" --resume %*
goto end

:end
if errorlevel 1 (
    echo.
    echo Claude Code saiu com erro ^(codigo %errorlevel%^).
    pause
)
endlocal
