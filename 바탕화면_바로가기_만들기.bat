@echo off
REM Create a Desktop shortcut for the app. All Korean text + logic lives in the
REM PowerShell script (UTF-8 with BOM), so this .bat stays pure ASCII to avoid
REM Windows codepage / line-continuation problems.
REM strip trailing backslash from %~dp0 (a trailing "...\" becomes an escaped quote).
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_shortcut.ps1" "%ROOT%"
echo.
pause
