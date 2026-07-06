# Fed-Watcher Daily Wake-up — PC 폴백 (클라우드 자동화가 모두 실패할 때만 필요)
#
# 매일 07:15 KST에 Render 백엔드를 깨워, 내부 스케줄러(07:30 브리핑 / 08:00 발표)가
# 실행되도록 한다. Windows 작업 스케줄러 등록 (관리자 PowerShell에서 1회 실행):
#
#   schtasks /Create /TN "FedWatcher Daily Wakeup" `
#     /TR "powershell -ExecutionPolicy Bypass -File C:\Users\andul\fed-watcher\scheduler\daily_update.ps1" `
#     /SC DAILY /ST 07:15
#
# 컴퓨터가 07:15에 꺼져/잠들어 있어도 켜지는 즉시 실행되게 하려면, 등록 후
# 작업 스케줄러 GUI에서 해당 작업 → 설정 → "예약된 시작 시간을 놓친 경우
# 가능한 대로 빨리 작업 시작"을 체크한다.

$Url     = "https://fed-watcher-backend-9rgk.onrender.com/health"
$LogFile = Join-Path $PSScriptRoot "..\logs\daily_update.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

function Ping-Backend($tag) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url`?pc=$tag" -TimeoutSec 120 -UseBasicParsing
        Write-Log "ping $tag → HTTP $($resp.StatusCode)"
        return $true
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code) {
            # 403 등 앱이 만든 응답이면 서버는 깨어 있는 것 — 성공으로 간주
            Write-Log "ping $tag → HTTP $code (app responded)"
            return $true
        }
        Write-Log "ping $tag → no response ($($_.Exception.Message))"
        return $false
    }
}

Write-Log "=== Daily wake-up started ==="

# 1) 깨우기: 콜드 스타트(1~3분)를 감안해 최대 10회, 60초 간격 재시도
$awake = $false
for ($i = 1; $i -le 10; $i++) {
    if (Ping-Backend "boot$i") { $awake = $true; break }
    Start-Sleep -Seconds 60
}

if (-not $awake) {
    Write-Log "FAILED: backend never responded — check the Render dashboard."
    exit 1
}

# 2) 07:30 브리핑과 08:00 발표 사이에 다시 잠들지 않도록 08:05까지 5분 간격 핑
$deadline = Get-Date -Hour 8 -Minute 5 -Second 0
$n = 0
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 300
    $n++
    Ping-Backend "keepalive$n" | Out-Null
}

Write-Log "=== Daily wake-up complete ==="
