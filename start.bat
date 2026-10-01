@echo off
chcp 65001 >nul
cd /d "%~dp0"
set OPEN_BROWSER=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo   RUNNING FROM THIS FOLDER:
echo   %~dp0
echo   (Update this SAME folder. If this path is not the one you
echo    updated, you have more than one copy - use only this one.)
echo ============================================================

REM ============================================================
REM  First run: auto-create the .venv and install packages.
REM  Already set up: just activate. (Nothing for the user to do.)
REM ============================================================
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [First-time setup] Creating a Python virtual environment and
  echo                    installing packages. This runs once, a few minutes...
  echo.
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo *** Python not found. Install Python 3.12 from
    echo     https://www.python.org/downloads/  and check "Add Python to PATH". ***
    pause
    exit /b 1
  )
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if not exist ".env" copy ".env.example" ".env" >nul
  copy /y requirements.txt ".venv\requirements.snapshot" >nul
) else (
  call ".venv\Scripts\activate.bat"
  REM Reinstall only when requirements.txt changed since last install (new packages).
  fc /b requirements.txt ".venv\requirements.snapshot" >nul 2>&1
  if errorlevel 1 (
    echo [Update] Installing new/updated packages...
    pip install -r requirements.txt
    copy /y requirements.txt ".venv\requirements.snapshot" >nul
  )
)

echo.
echo Stopping any old server on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   Starting server... the browser opens in a moment.
echo   This black window IS the server. Do NOT close it while using the app.
echo   If the browser does not open, go to:  http://localhost:8000
echo ============================================================
echo.
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
echo.
echo *** Server stopped. If there is an error above, tell me. ***
pause
