@echo off
chcp 65001 >nul
cd /d "%~dp0"
set OPEN_BROWSER=1
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
"%VENVPY%" -c "import uvicorn, fastapi" 1>nul 2>nul || set "NEED_INSTALL=1"
fc /b requirements.txt ".venv\requirements.snapshot" >nul 2>&1 || set "NEED_INSTALL=1"
if defined NEED_INSTALL call :install
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

REM re-check: if still broken, the install failed -> show it and stop
"%VENVPY%" -c "import uvicorn, fastapi" 1>nul 2>nul
if errorlevel 1 goto :install_failed

REM 3) free port 8000 and run (venv python by full path; backend opens the browser)
echo.
echo Stopping any old server on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   Starting server... the browser opens in a moment.
echo   This black window IS the server. Do NOT close it while using the app.
echo   If the browser does not open, go to:  http://localhost:8000
echo ============================================================
"%VENVPY%" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
echo.
echo *** Server stopped. If there is an error above, tell me. ***
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
echo     then delete the ".venv" folder in this folder and run again. ***
pause
exit /b 1

:no_python
echo.
echo *** Python not found. Install Python 3.12 from https://www.python.org/downloads/
echo     and check "Add Python to PATH". Then run this again. ***
pause
exit /b 1
