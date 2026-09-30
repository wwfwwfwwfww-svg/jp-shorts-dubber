@echo off
chcp 65001 >nul
cd /d "%~dp0"
set OPEN_BROWSER=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ============================================================
REM  최초 실행이면 가상환경(.venv)을 자동으로 만들고 패키지를 설치합니다.
REM  이미 있으면 그냥 켭니다. (사용자가 손댈 것 없음)
REM ============================================================
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [최초 설정] 파이썬 가상환경을 만들고 필요한 패키지를 설치합니다.
  echo            처음 한 번만 하며, 몇 분 걸릴 수 있어요...
  echo.
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo *** 파이썬을 찾지 못했습니다. https://www.python.org/downloads/ 에서
    echo     Python 3.12를 설치할 때 "Add Python to PATH"를 체크하세요. ***
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
  REM requirements.txt가 지난 설치 이후 바뀌었으면(=새 패키지 추가) 그때만 다시 설치
  fc /b requirements.txt ".venv\requirements.snapshot" >nul 2>&1
  if errorlevel 1 (
    echo [업데이트] 새 패키지를 설치합니다...
    pip install -r requirements.txt
    copy /y requirements.txt ".venv\requirements.snapshot" >nul
  )
)

echo.
echo Stopping any old server on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
echo.
echo ============================================================
echo   서버를 시작합니다... 잠시 후 브라우저가 자동으로 열립니다.
echo   이 창(검은 창)은 서버입니다. 사용하는 동안 닫지 마세요.
echo   브라우저가 안 열리면 직접 접속:  http://localhost:8000
echo ============================================================
echo.
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
echo.
echo *** 서버가 종료되었습니다. 위에 오류가 있으면 알려주세요. ***
pause
