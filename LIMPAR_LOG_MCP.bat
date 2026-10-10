@echo off
setlocal
cd /d "%~dp0"
if exist "data\mcp\handshake.log" del /q "data\mcp\handshake.log"
echo Log MCP limpo.
pause
