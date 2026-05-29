# Claude Auth Helper - 더블클릭으로 실행하세요
# 이 스크립트는 claude auth login을 자동으로 처리합니다

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName PresentationFramework

Write-Host "=== Claude Auth Helper ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: claude auth login 시작하고 URL 캡처
Write-Host "claude auth login 시작..." -ForegroundColor Yellow

$tempIn = "$env:TEMP\claude_stdin.txt"
$tempOut = "$env:TEMP\claude_stdout.txt"

# 빈 파일로 시작 (나중에 코드 입력)
"" | Out-File -FilePath $tempIn -Encoding utf8

# claude auth login을 별도 프로세스로 시작
$procInfo = New-Object System.Diagnostics.ProcessStartInfo
$procInfo.FileName = "claude"
$procInfo.Arguments = "auth login"
$procInfo.UseShellExecute = $false
$procInfo.RedirectStandardOutput = $true
$procInfo.RedirectStandardInput = $true
$procInfo.RedirectStandardError = $true
$procInfo.CreateNoWindow = $false

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $procInfo
$proc.Start() | Out-Null

Write-Host "프로세스 시작됨 (PID: $($proc.Id))" -ForegroundColor Green
Write-Host ""

# URL 나올 때까지 기다림
$url = ""
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline -and $url -eq "") {
    Start-Sleep -Milliseconds 500
    $line = $proc.StandardOutput.ReadLine()
    if ($line -match "https://") {
        $url = $line.Trim()
    }
}

if ($url -eq "") {
    Write-Host "URL을 찾지 못했습니다. 수동으로 진행하세요." -ForegroundColor Red
    exit 1
}

Write-Host "인증 URL:" -ForegroundColor Cyan
Write-Host $url
Write-Host ""

# 브라우저 자동으로 열기
Start-Process $url
Write-Host "브라우저가 열렸습니다." -ForegroundColor Green
Write-Host ""

# 팝업으로 코드 입력받기
$msgResult = [System.Windows.Forms.MessageBox]::Show(
    "브라우저에서 Claude 계정으로 로그인하세요.`n`n로그인 후 나타나는 코드를 클립보드에 복사(Ctrl+A, Ctrl+C)한 다음`n`n[OK]를 클릭하세요.",
    "Claude 인증",
    [System.Windows.Forms.MessageBoxButtons]::OKCancel,
    [System.Windows.Forms.MessageBoxIcon]::Information
)

if ($msgResult -eq "Cancel") {
    Write-Host "취소됨" -ForegroundColor Red
    $proc.Kill()
    exit 1
}

# 클립보드에서 코드 가져오기
$code = [System.Windows.Forms.Clipboard]::GetText().Trim()
Write-Host "클립보드에서 코드 가져옴: $($code.Substring(0, [Math]::Min(20, $code.Length)))..." -ForegroundColor Green

# 코드를 프로세스 stdin으로 전송
$proc.StandardInput.WriteLine($code)
$proc.StandardInput.Close()

Write-Host "코드 전송 완료. 응답 기다리는 중..." -ForegroundColor Yellow
$proc.WaitForExit(15000)

Write-Host ""
Write-Host "=== 결과 확인 ===" -ForegroundColor Cyan

$credsPath = "$env:USERPROFILE\.claude\.credentials.json"
$creds = Get-Content $credsPath -Raw -ErrorAction SilentlyContinue

if ($creds -like "*claudeAiOauth*") {
    Write-Host "SUCCESS! 인증 완료!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=== CREDENTIALS (아래 내용을 복사하세요) ===" -ForegroundColor Yellow
    Write-Host $creds
    Write-Host "========================================" -ForegroundColor Yellow
    
    # 클립보드에도 복사
    [System.Windows.Forms.Clipboard]::SetText($creds)
    Write-Host ""
    Write-Host "클립보드에도 자동 복사됨!" -ForegroundColor Green
} else {
    Write-Host "인증 실패 또는 미완료." -ForegroundColor Red
    Write-Host "현재 credentials 파일:" -ForegroundColor Yellow
    Write-Host $creds
}

Write-Host ""
Write-Host "아무 키나 누르면 종료..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
