@echo off
chcp 65001 >nul
cd /d "%~dp0subtitle-remover"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "VENVPY=.venv\Scripts\python.exe"

echo ============================================================
echo   RUNNING FROM THIS FOLDER:
echo   %~dp0
echo   Update this SAME folder. Multiple copies cause trouble.
echo ============================================================

REM 1) venv python missing -> create the virtual environment
if not exist "%VENVPY%" call :make_venv
if not exist "%VENVPY%" goto :no_python

REM 2) make sure key packages really import (a broken/half-done venv has none);
REM    also reinstall when requirements.txt changed. Run with the venv python by
REM    FULL PATH so the system Python is never used by accident.
set "NEED_INSTALL="
"%VENVPY%" -c "import uvicorn, fastapi, cv2" 1>nul 2>nul || set "NEED_INSTALL=1"
fc /b requirements.txt ".venv\requirements.snapshot" >nul 2>&1 || set "NEED_INSTALL=1"
if defined NEED_INSTALL call :install

REM re-check: if still broken, the install failed -> show it and stop
"%VENVPY%" -c "import uvicorn, fastapi, cv2" 1>nul 2>nul
if errorlevel 1 goto :install_failed

REM make sure the UI files are present (a partial/incomplete copy can miss them)
if not exist "static\index.html" goto :files_missing
if not exist "app.py" goto :files_missing

REM 3) free port 8008 and run (venv python by full path)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8008" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   Subtitle Eraser starting... the browser opens automatically.
echo   Do NOT close this window.   URL: http://localhost:8008
echo ============================================================
start "" http://localhost:8008
"%VENVPY%" -m uvicorn app:app --host 127.0.0.1 --port 8008
echo.
echo *** Stopped. If there is an error above, tell me. ***
pause
exit /b 0

:make_venv
echo [Setup] Creating Python environment...
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
exit /b 0

:install
echo.
echo [Setup] Installing packages. The first time takes a few minutes...
"%VENVPY%" -m pip install --upgrade pip
"%VENVPY%" -m pip install -r requirements.txt
copy /y requirements.txt ".venv\requirements.snapshot" >nul
exit /b 0

:install_failed
echo.
echo *** Package install failed (see errors above). Check your internet,
echo     then delete the ".venv" folder inside "subtitle-remover" and run again. ***
pause
exit /b 1

:files_missing
echo.
echo *** UI files are missing (the "static" folder is incomplete).
echo     This copy is broken. Run the UPDATE batch file in this folder to
echo     restore all files, then run this again. ***
pause
exit /b 1

:no_python
echo.
echo *** Python not found. Install Python 3.12 from https://www.python.org/downloads/
echo     and check "Add Python to PATH". Then run this again. ***
pause
exit /b 1
