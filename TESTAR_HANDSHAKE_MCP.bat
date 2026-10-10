@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 TESTAR_HANDSHAKE_MCP.py
) else (
  python TESTAR_HANDSHAKE_MCP.py
)
echo.
echo Este teste nao chama Codex, ChatGPT ou API.
pause
