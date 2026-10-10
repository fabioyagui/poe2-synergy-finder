@echo off
setlocal
cd /d "%~dp0"
if not exist "data\mcp\handshake.log" (
  echo O log ainda nao existe.
  echo Abra o Codex, use /mcp e tente iniciar synergy-finder primeiro.
  pause
  exit /b 1
)
notepad "data\mcp\handshake.log"
