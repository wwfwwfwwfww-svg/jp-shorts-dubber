@echo off
REM Update the app in place (code only). Keeps data/, .env, .venv untouched.
REM Korean text + logic live in the PowerShell script (UTF-8 BOM); this .bat is ASCII.
REM NOTE: strip the trailing backslash from %~dp0 — passing "...\" to an exe makes
REM \" an escaped quote, which puts a stray " into the path and breaks robocopy.
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" "%ROOT%"
echo.
pause
