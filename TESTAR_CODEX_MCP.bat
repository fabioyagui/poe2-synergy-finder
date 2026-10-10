@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 mcp_server.py --self-test
) else (
  python mcp_server.py --self-test
)
echo.
echo Se o Finder estava aberto, a ultima linha deve ser OK.
echo O teste nao usa tokens nem chama nenhum modelo.
pause
