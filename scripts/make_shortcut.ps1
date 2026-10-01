param([string]$Root)

# 프로젝트 루트 결정: 배치에서 인자로 넘겨받거나, 스크립트 위치(scripts/)의 상위 폴더.
if (-not $Root) {
  $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
# 방어: 배치에서 "...\" 가 넘어오며 끝에 따옴표가 박히는 경우 제거.
$Root = $Root.Trim().Trim('"').TrimEnd('\')

$name    = '쇼츠 스튜디오 (더빙+소재찾기)'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop ($name + '.lnk')

try {
  $sh = New-Object -ComObject WScript.Shell
  $s  = $sh.CreateShortcut($lnkPath)
  $s.TargetPath       = Join-Path $Root 'start.bat'
  $s.WorkingDirectory = $Root
  $s.IconLocation     = "$env:SystemRoot\System32\shell32.dll,220"
  $s.Description       = '일본어 쇼츠 더빙 + 소재 찾기 (로컬 웹앱)'
  $s.Save()
  Write-Host ''
  Write-Host ('[완료] 바탕화면에 "' + $name + '" 바로가기를 만들었습니다.')
} catch {
  Write-Host ''
  Write-Host ('[오류] 바로가기 생성 실패: ' + $_.Exception.Message)
}

# .env 준비: 없으면 예시에서 복사하고 메모장으로 열어 키 입력 안내
$envPath = Join-Path $Root '.env'
$example = Join-Path $Root '.env.example'
if (-not (Test-Path $envPath)) {
  if (Test-Path $example) { Copy-Item $example $envPath }
  Write-Host ''
  Write-Host '[안내] API 키 입력 파일(.env)을 메모장으로 엽니다.'
  Write-Host '       ANTHROPIC_API_KEY(더빙) / YOUTUBE_API_KEY(소재 찾기) 등을 채워 저장하세요.'
  if (Test-Path $envPath) { Start-Process notepad $envPath }
}

Write-Host ''
Write-Host '이제 바탕화면의 아이콘을 더블클릭하면 프로그램이 실행됩니다.'
Write-Host '(처음 실행 시 자동으로 설치가 진행되니 잠시 기다려 주세요.)'
Write-Host ''
