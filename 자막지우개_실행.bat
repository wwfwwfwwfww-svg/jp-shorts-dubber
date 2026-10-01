@echo off
chcp 65001 >nul
cd /d "%~dp0subtitle-remover"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM First run: make its own venv (separate from the main app) and install.
if not exist ".venv\Scripts\python.exe" (
  echo [First-time setup] Creating environment and installing packages (a few minutes)...
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo *** Python not found. Install Python 3.12 from https://www.python.org/downloads/
    echo     and check "Add Python to PATH". ***
    pause
    exit /b 1
  )
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  copy /y requirements.txt ".venv\requirements.snapshot" >nul
) else (
  call ".venv\Scripts\activate.bat"
  fc /b requirements.txt ".venv\requirements.snapshot" >nul 2>&1
  if errorlevel 1 (
    echo [Update] Installing new packages...
    pip install -r requirements.txt
    copy /y requirements.txt ".venv\requirements.snapshot" >nul
  )
)

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8008" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   Subtitle Eraser starting... the browser opens automatically.
echo   Do NOT close this window.   URL: http://localhost:8008
echo ============================================================
start "" http://localhost:8008
python -m uvicorn app:app --host 127.0.0.1 --port 8008
echo.
echo *** Stopped. If there is an error above, tell me. ***
pause
