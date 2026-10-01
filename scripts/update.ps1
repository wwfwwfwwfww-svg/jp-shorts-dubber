param([string]$Root)

# 프로젝트 루트: 배치에서 인자로 받거나 스크립트(scripts/)의 상위 폴더.
if (-not $Root) {
  $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$Root = $Root.TrimEnd('\')

$zipUrl = 'https://github.com/wwfwwfwwfww-svg/jp-shorts-dubber/archive/refs/heads/main.zip'
$tmp = Join-Path $env:TEMP ('jpupd_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
$zip = Join-Path $tmp 'main.zip'

try {
  Write-Host ''
  Write-Host '[1/3] 최신 코드를 내려받는 중...'
  $ProgressPreference = 'SilentlyContinue'
  Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing

  Write-Host '[2/3] 압축 푸는 중...'
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $src = Join-Path $tmp 'jp-shorts-dubber-main'
  if (-not (Test-Path $src)) {
    Write-Host '[오류] 내려받은 폴더를 찾지 못했습니다.'
    exit 1
  }

  Write-Host '[3/3] 코드 갱신 중... (data / .env / .venv 는 그대로 유지)'
  # robocopy: 코드만 덮어씀. data/.venv/.git/__pycache__ 폴더와 .env/*.log 파일은 제외.
  # /IS /IT : 같아 보여도(타임스탬프/크기) 강제로 덮어쓴다(일부 파일만 갱신되는 문제 방지).
  # /MIR 아님 → 기존 파일 삭제는 없음(안전).
  robocopy $src $Root /E /IS /IT /XD data .venv .git __pycache__ /XF .env *.log *.snapshot | Out-Null
  $rc = $LASTEXITCODE   # robocopy: 0~7 정상, 8 이상 실패

  Write-Host ''
  if ($rc -ge 8) {
    Write-Host ('[오류] 파일 복사 실패(코드 ' + $rc + '). 폴더가 다른 프로그램에서 열려 있지 않은지 확인하고 다시 시도하세요.')
  } else {
    Write-Host '업데이트 완료! 기존에 찾아둔 영상(data)과 API 키(.env)는 그대로입니다.'
    Write-Host '이제 바탕화면 아이콘(또는 start.bat)으로 실행하세요.'
    Write-Host '(패키지가 바뀐 경우 다음 실행 때 자동으로 재설치됩니다.)'
  }

  # 어느 폴더에 무슨 버전이 설치됐는지 명확히 표시(폴더가 여러 개일 때 혼란 방지).
  Write-Host ''
  Write-Host '============================================================'
  Write-Host ('  업데이트한 폴더: ' + $Root)
  $appPy = Join-Path $Root 'subtitle-remover\app.py'
  if (Test-Path $appPy) {
    $buildLine = Select-String -Path $appPy -Pattern '^BUILD\s*=' -SimpleMatch:$false | Select-Object -First 1
    if ($buildLine) { Write-Host ('  자막지우개 버전: ' + $buildLine.Line.Trim()) }
  }
  Write-Host '  ※ 이 폴더의 실행 파일(자막지우개_실행.bat / start.bat)로 실행하세요.'
  Write-Host '============================================================'
} catch {
  Write-Host ''
  Write-Host ('[오류] 업데이트 실패: ' + $_.Exception.Message)
  Write-Host '인터넷 연결을 확인하거나, 잠시 후 다시 시도하세요.'
} finally {
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
