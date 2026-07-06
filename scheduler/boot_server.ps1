# Fed-Watcher Boot Script — Triggered at 12:00 PM KST daily
# Register via Windows Task Scheduler

$ProjectDir = "C:\Users\andul\fed-watcher"
$LogFile    = "$ProjectDir\logs\boot.log"

New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

Write-Log "=== Boot triggered ==="

# Sync to master before launching, so every boot brings the PC up on the same
# code as the cloud (Render / onrender.com). Untracked .env / data survive a
# hard reset; if git is unavailable we boot on the existing checkout.
Push-Location $ProjectDir
try {
    git fetch origin master --quiet 2>&1 | ForEach-Object { Write-Log "  git: $_" }
    git reset --hard origin/master 2>&1 | ForEach-Object { Write-Log "  git: $_" }
    Write-Log "synced to origin/master: $(git rev-parse --short HEAD 2>$null)"
} catch {
    Write-Log "git sync skipped ($_) — booting on existing checkout."
} finally {
    Pop-Location
}

# Verify KST time (UTC+9)
$kst = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
    [DateTime]::UtcNow, "Korea Standard Time"
)
Write-Log "KST: $kst"

# Start backend (uvicorn)
$backendJob = Start-Process -FilePath "python" `
    -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000" `
    -WorkingDirectory $ProjectDir `
    -PassThru `
    -RedirectStandardOutput "$ProjectDir\logs\backend.log" `
    -RedirectStandardError  "$ProjectDir\logs\backend_err.log"

Write-Log "Backend started PID: $($backendJob.Id)"

# Start frontend (Next.js)
$frontendJob = Start-Process -FilePath "npm" `
    -ArgumentList "start" `
    -WorkingDirectory "$ProjectDir\frontend" `
    -PassThru `
    -RedirectStandardOutput "$ProjectDir\logs\frontend.log" `
    -RedirectStandardError  "$ProjectDir\logs\frontend_err.log"

Write-Log "Frontend started PID: $($frontendJob.Id)"

# Save PIDs for shutdown script
"$($backendJob.Id)" | Out-File "$ProjectDir\.backend.pid" -Encoding utf8
"$($frontendJob.Id)" | Out-File "$ProjectDir\.frontend.pid" -Encoding utf8

Write-Log "Boot complete."
