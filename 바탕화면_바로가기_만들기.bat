@echo off
REM Create a Desktop shortcut for the app. All Korean text + logic lives in the
REM PowerShell script (UTF-8 with BOM), so this .bat stays pure ASCII to avoid
REM Windows codepage / line-continuation problems.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_shortcut.ps1" "%~dp0"
echo.
pause
