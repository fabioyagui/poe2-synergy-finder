@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 TESTAR_9_MCP_REAIS.py
) else (
  python TESTAR_9_MCP_REAIS.py
)
pause
