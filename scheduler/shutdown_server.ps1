# Fed-Watcher Shutdown Script — Triggered at 08:30 AM KST daily

$ProjectDir = "C:\Users\andul\fed-watcher"
$LogFile    = "$ProjectDir\logs\shutdown.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

Write-Log "=== Shutdown triggered ==="

# Graceful shutdown via API (gives backend 30s to finish in-flight requests)
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/internal/shutdown" -Method POST -TimeoutSec 5
    Write-Log "Graceful shutdown signal sent."
    Start-Sleep 30
} catch {
    Write-Log "Graceful shutdown failed, forcing."
}

# Kill by saved PIDs
foreach ($pidFile in @("$ProjectDir\.backend.pid", "$ProjectDir\.frontend.pid")) {
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile -Raw
        if ($pid) {
            try {
                Stop-Process -Id ([int]$pid.Trim()) -Force -ErrorAction Stop
                Write-Log "Killed PID $($pid.Trim())"
            } catch {
                Write-Log "PID $($pid.Trim()) already gone."
            }
        }
        Remove-Item $pidFile -Force
    }
}

# Fallback: kill by process name
Get-Process "python","node" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Log "Shutdown complete."
