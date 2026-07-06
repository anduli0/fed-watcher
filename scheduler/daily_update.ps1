# KRW-Watcher daily morning update — PC fallback runner
# Registered at 06:45 KST so the cycle + briefing COMPLETE before 08:00.
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

# The live build doesn't expose forecast.created_kst — the reliable signal
# is /api/agents run.completed_at (last finished committee cycle).
$needCycle  = $true
$runIdBefore = $null
try {
    $ag = Invoke-RestMethod -Uri "$BaseUrl/api/agents" -TimeoutSec 20
    $runIdBefore = $ag.run.id
    $completed   = [DateTime]::Parse($ag.run.completed_at)
    if ($completed.ToString("yyyy-MM-dd") -eq $today -and $completed.TimeOfDay -ge [TimeSpan]"06:30") {
        $needCycle = $false
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
    } catch { Write-Log "briefing generate failed: $_" }
}

# ── 4. Forecast cycle (async endpoint; poll run.id until it changes) ────────
if ($needCycle) {
    Write-Log "POST /api/cycle ..."
    try {
        $resp = Invoke-RestMethod -Uri "$BaseUrl/api/cycle" -Method Post -TimeoutSec 60
        Write-Log "cycle response: $($resp.status)"
    } catch { Write-Log "cycle start failed: $_"; exit 1 }

    for ($i = 1; $i -le 80; $i++) {
        Start-Sleep -Seconds 30
        try {
            $ag = Invoke-RestMethod -Uri "$BaseUrl/api/agents" -TimeoutSec 20
            if ($ag.run.id -and $ag.run.id -ne $runIdBefore) {
                Write-Log "cycle complete: run.id=$($ag.run.id) completed_at=$($ag.run.completed_at)"
                break
            }
        } catch {}
        if ($i -eq 80) { Write-Log "WARNING: no new run after 40 min — cycle may have failed; cloud sweeps will retry." }
    }
}

Write-Log "Daily update finished."
