# KRW-Watcher daily morning update — PC repair runner
# Registered at 07:45 KST: the app's own scheduler completes the morning
# cycle ~07:30 KST, so this only repairs mornings the internal schedule
# missed (e.g. the app was down at 07:30). Register via
# scheduler/register_daily_update_krw.ps1 (Windows Task Scheduler).
# (scheduler/daily_update.ps1 is the separate Fed-Watcher wake-up fallback.)
# Idempotent: exits immediately when today's morning result already exists.
#
# NOTE: POSTs through the funnel URL are rejected with 401 (external), so
# this runs against localhost where the app itself listens.

param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ProjectDir = "C:\Users\andul\fed-watcher"
$LogFile    = "$ProjectDir\logs\daily_update_krw.log"
New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

$BaseUrl = $BaseUrl.TrimEnd("/")
Write-Log "=== Daily update check (target: $BaseUrl) ==="

# ── 1. Reach the app (localhost first — funnel URL 401s on POST) ────────────
$reachable = $null
foreach ($candidate in @($BaseUrl, "https://krw-watcher.tail3e31a9.ts.net")) {
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
    Write-Log "ERROR: app unreachable — is the server running? (scheduler/boot_server.ps1)"
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

# The live build's /api/agents run.completed_at is a naive timestamp that is
# actually UTC (measured: internal 07:30 KST cycle logs 22:30 previous-day).
# Interpret it BOTH ways (UTC and KST) — fresh if either reading says the
# last cycle completed today >= 06:00 KST.
$needCycle   = $true
$runIdBefore = $null
try {
    $ag = Invoke-RestMethod -Uri "$BaseUrl/api/agents" -TimeoutSec 20
    $runIdBefore = $ag.run.id
    $naive = [DateTime]::Parse($ag.run.completed_at)
    $asUtc = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
        [DateTime]::SpecifyKind($naive, "Utc"), "Korea Standard Time")
    foreach ($cand in @($naive, $asUtc)) {
        if ($cand.ToString("yyyy-MM-dd") -eq $today -and $cand.Hour -ge 6) { $needCycle = $false }
    }
    Write-Log "last run: id=$($ag.run.id) completed_at=$($ag.run.completed_at) -> needCycle=$needCycle"
} catch { Write-Log "run check failed: $_" }

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
    } catch { Write-Log "briefing generate failed (401 = app requires auth even locally; its internal scheduler will handle it): $_" }
}

# ── 4. Forecast cycle (async endpoint; poll run.id until it changes) ────────
if ($needCycle) {
    Write-Log "POST /api/cycle ..."
    try {
        $resp = Invoke-RestMethod -Uri "$BaseUrl/api/cycle" -Method Post -TimeoutSec 60
        Write-Log "cycle response: $($resp.status)"
    } catch { Write-Log "cycle start failed (401 = app requires auth even locally): $_"; exit 1 }

    for ($i = 1; $i -le 80; $i++) {
        Start-Sleep -Seconds 30
        try {
            $ag = Invoke-RestMethod -Uri "$BaseUrl/api/agents" -TimeoutSec 20
            if ($ag.run.id -and $ag.run.id -ne $runIdBefore) {
                Write-Log "cycle complete: run.id=$($ag.run.id) completed_at=$($ag.run.completed_at)"
                break
            }
        } catch {}
        if ($i -eq 80) { Write-Log "WARNING: no new run after 40 min — cycle may have failed." }
    }
}

Write-Log "Daily update finished."
