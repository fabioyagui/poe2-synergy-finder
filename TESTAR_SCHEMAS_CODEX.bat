@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 TESTAR_SCHEMAS_CODEX.py
) else (
  python TESTAR_SCHEMAS_CODEX.py
)
pause
