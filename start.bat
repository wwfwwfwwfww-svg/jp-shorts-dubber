@echo off
cd /d "%~dp0"
set OPEN_BROWSER=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call ".venv\Scripts\activate.bat"
echo.
echo Stopping any old server on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   Starting server (fresh)... browser opens in a moment.
echo   Do NOT close this window while using the app.
echo   If browser does not open: go to  http://localhost:8000
echo ============================================================
echo.
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
echo.
echo *** Server stopped. If there is an error above, tell me. ***
pause
