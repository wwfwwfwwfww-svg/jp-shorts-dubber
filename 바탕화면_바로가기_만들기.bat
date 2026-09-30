@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "NAME=쇼츠 스튜디오 (더빙+소재찾기)"

echo.
echo 바탕화면에 "%NAME%" 바로가기를 만듭니다...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop=[Environment]::GetFolderPath('Desktop');" ^
  "$lnk=Join-Path $desktop '%NAME%.lnk';" ^
  "$sh=New-Object -ComObject WScript.Shell;" ^
  "$s=$sh.CreateShortcut($lnk);" ^
  "$s.TargetPath='%~dp0start.bat';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%SystemRoot%\System32\shell32.dll,220';" ^
  "$s.Description='일본어 쇼츠 더빙 + 소재 찾기 (로컬 웹앱)';" ^
  "$s.Save();"

if errorlevel 1 (
  echo *** 바로가기 생성에 실패했습니다. 이 파일을 마우스 오른쪽 클릭 → '관리자 권한으로 실행'을 시도해 보세요. ***
  pause
  exit /b 1
)

REM .env 파일이 없으면 예시에서 복사하고 메모장으로 열어 키 입력을 안내
if not exist ".env" (
  if exist ".env.example" copy ".env.example" ".env" >nul
  echo.
  echo [안내] API 키 입력 파일(.env)을 메모장으로 엽니다.
  echo        ANTHROPIC_API_KEY(더빙) / YOUTUBE_API_KEY(소재 찾기) 등을 채워 저장하세요.
  echo        (YOUTUBE_API_KEY는 앱의 소재찾기 탭 - 설정 화면에서 입력해도 됩니다.)
  start "" notepad ".env"
)

echo.
echo 완료! 이제 바탕화면의 "%NAME%" 아이콘을 더블클릭하면 프로그램이 실행됩니다.
echo (처음 실행 시 자동으로 설치가 진행되니 잠시 기다려 주세요.)
echo.
pause
