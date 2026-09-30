@echo off
REM Update the app in place (code only). Keeps data/, .env, .venv untouched.
REM Korean text + logic live in the PowerShell script (UTF-8 BOM); this .bat is ASCII.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" "%~dp0"
echo.
pause
