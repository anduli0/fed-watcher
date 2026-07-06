# KRW-Watcher daily 08:00 KST update — PC fallback runner
# Register via scheduler/register_daily_update.ps1 (Windows Task Scheduler).
# Idempotent: skips work already done today, so it can run alongside the
# GitHub Actions / Claude Routine cloud path without double token spend.

param(
    [string]$BaseUrl = "https://krw-watcher.tail3e31a9.ts.net"
)

$ProjectDir = "C:\Users\andul\fed-watcher"
$LogFile    = "$ProjectDir\logs\daily_update.log"
New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

$BaseUrl = $BaseUrl.TrimEnd("/")
Write-Log "=== Daily update triggered (target: $BaseUrl) ==="

# ── 1. Wake / reach the site (localhost fallback since the app runs here) ───
$reachable = $null
foreach ($candidate in @($BaseUrl, "http://localhost:8000")) {
    for ($i = 1; $i -le 8; $i++) {
        try {
            $health = Invoke-RestMethod -Uri "$candidate/health" -TimeoutSec 20
            Write-Log "health OK via ${candidate}: model=$($health.model) agents=$($health.agent_count)"
            $reachable = $candidate
            break
        } catch {
            Write-Log "  [$i] $candidate not answering, retrying in 15s..."
            Start-Sleep -Seconds 15
        }
    }
    if ($reachable) { break }
}
if (-not $reachable) {
    Write-Log "ERROR: site unreachable — is the server running? (scheduler/boot_server.ps1)"
    exit 1
}
$BaseUrl = $reachable

# ── 2. Freshness check — skip anything already done today (KST) ─────────────
$kst   = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "Korea Standard Time")
$today = $kst.ToString("yyyy-MM-dd")

$needBrief = $true
try {
    $latest = Invoke-RestMethod -Uri "$BaseUrl/api/briefing/latest" -TimeoutSec 20
    if ($latest.brief.date -eq $today) { $needBrief = $false }
    Write-Log "latest briefing: $($latest.brief.date) (today=$today) -> needBrief=$needBrief"
} catch { Write-Log "briefing check failed: $_" }

$needCycle = $true
try {
    $fc = Invoke-RestMethod -Uri "$BaseUrl/api/forecast" -TimeoutSec 20
    if ($fc.created_kst -and $fc.created_kst.StartsWith($today)) {
        $hour = [int]$fc.created_kst.Substring(11, 2)
        if ($hour -ge 7) { $needCycle = $false }
    }
    Write-Log "forecast created_kst: $($fc.created_kst) -> needCycle=$needCycle"
} catch { Write-Log "forecast check failed: $_" }

if (-not $needBrief -and -not $needCycle) {
    Write-Log "Already updated today — nothing to do."
    exit 0
}

# ── 3. Daily briefing (blocking endpoint) ────────────────────────────────────
if ($needBrief) {
    Write-Log "POST /api/briefing/generate ..."
    try {
        $brief = Invoke-RestMethod -Uri "$BaseUrl/api/briefing/generate" -Method Post -TimeoutSec 900
        $briefDate = if ($brief.brief.date) { $brief.brief.date } else { $brief.date }
        Write-Log "briefing done: $briefDate"
    } catch { Write-Log "briefing generate failed: $_" }
}

# ── 4. Forecast cycle (async endpoint; poll until the forecast changes) ─────
if ($needCycle) {
    $before = ""
    try { $before = (Invoke-RestMethod -Uri "$BaseUrl/api/forecast" -TimeoutSec 20 | ConvertTo-Json -Depth 10 -Compress) } catch {}
    Write-Log "POST /api/cycle ..."
    try {
        $resp = Invoke-RestMethod -Uri "$BaseUrl/api/cycle" -Method Post -TimeoutSec 60
        Write-Log "cycle response: $($resp.status)"
    } catch { Write-Log "cycle start failed: $_"; exit 1 }

    for ($i = 1; $i -le 140; $i++) {
        Start-Sleep -Seconds 15
        try {
            $now = (Invoke-RestMethod -Uri "$BaseUrl/api/forecast" -TimeoutSec 20 | ConvertTo-Json -Depth 10 -Compress)
            if ($now -and $now -ne $before) { Write-Log "forecast updated — cycle complete."; break }
        } catch {}
        if ($i -eq 140) { Write-Log "WARNING: forecast unchanged after 35 min — cycle may still be running." }
    }
}

Write-Log "Daily update finished."
