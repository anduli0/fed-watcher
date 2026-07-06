# sync_krw.ps1 — keep the PC's krw-watcher in lock-step with the repo (master).
#
# The PC, the Render service, and onrender.com must all run the SAME code. The
# Render service auto-deploys from master on every push; this script is the
# PC's equivalent — it pulls master and restarts the local krw-watcher app so
# a code change (e.g. the daily-report upgrade) reaches the PC automatically.
#
# Design goals:
#   * Root fix: the PC becomes a pure consumer of origin/master (hard reset),
#     so it can never silently drift behind the cloud again.
#   * Safe restart: only a process whose command line matches krw-watcher's
#     `app.main:app` is ever touched — the Fed-Watcher `backend.main:app` on
#     the same port is explicitly excluded, so this never kills the wrong app.
#   * Universal: auto-detects Docker vs. bare uvicorn; if neither is found the
#     freshly-reset code simply takes effect on the next boot (boot_server.ps1).
#   * Idempotent: when master hasn't moved, it does nothing but log.
#
# Untracked files (.env, data/) are preserved — hard reset only rewrites
# tracked files, and this script never runs `git clean`.
#
# Called at the top of daily_update_krw.ps1; can also be run standalone:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scheduler\sync_krw.ps1

param(
    [string]$ProjectDir = "C:\Users\andul\fed-watcher",
    [int]$Port = 8000
)

$LogFile = "$ProjectDir\logs\sync_krw.log"
New-Item -ItemType Directory -Force -Path "$ProjectDir\logs" | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
    Write-Host $msg
}

Write-Log "=== krw-watcher git sync ==="

# ── 1. Pull master (PC is a pure consumer of the cloud's source of truth) ────
Push-Location $ProjectDir
try {
    $before = (git rev-parse HEAD 2>$null)
    git fetch origin master --quiet 2>&1 | ForEach-Object { Write-Log "  git: $_" }
    # Hard-reset the tracked tree to origin/master. Untracked .env/data survive.
    git reset --hard origin/master 2>&1 | ForEach-Object { Write-Log "  git: $_" }
    $after = (git rev-parse HEAD 2>$null)
    $changed = @(git diff --name-only $before $after 2>$null)
} catch {
    Write-Log "ERROR: git sync failed: $_"
    Pop-Location
    exit 1
} finally {
    Pop-Location
}

if ($before -eq $after) {
    Write-Log "Already in sync with origin/master ($after). No restart needed."
    exit 0
}
Write-Log "Updated $before -> $after"

$krwTouched = $changed | Where-Object { $_ -like "krw-watcher/*" }
if (-not $krwTouched) {
    Write-Log "master moved but no krw-watcher/ files changed — no restart needed."
    exit 0
}
Write-Log "krw-watcher changed ($($krwTouched.Count) files) — restarting the app."

# ── 2. Restart, auto-detecting how krw-watcher runs on this machine ──────────
function Test-KrwHealth([int]$p) {
    for ($i = 1; $i -le 9; $i++) {
        try {
            $h = Invoke-RestMethod -Uri "http://localhost:$p/health" -TimeoutSec 10
            if ($h.agent_count) { return $true }   # krw health has agent_count
        } catch {}
        Start-Sleep -Seconds 10
    }
    return $false
}

$restarted = $false

# 2a. Docker — a container built from krw-watcher/ (rebuild so new code lands).
try {
    $krwContainer = (docker ps --format "{{.Names}}" 2>$null |
        Select-String -Pattern "krw" | Select-Object -First 1)
    if ($krwContainer) {
        $name = "$krwContainer".Trim()
        Write-Log "Docker container '$name' detected — rebuilding image & restarting."
        Push-Location "$ProjectDir\krw-watcher"
        try {
            docker build -t krw-watcher:latest . 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Log "  docker: $_" }
            docker rm -f $name 2>&1 | Out-Null
            docker run -d --name $name --restart unless-stopped -p "${Port}:8000" `
                --env-file "$ProjectDir\krw-watcher\.env" krw-watcher:latest 2>&1 | ForEach-Object { Write-Log "  docker: $_" }
            $restarted = $true
        } catch { Write-Log "  docker restart failed: $_" }
        finally { Pop-Location }
    }
} catch { Write-Log "  (docker not available: $($_.Exception.Message))" }

# 2b. Bare uvicorn — a python process running krw's `app.main:app` (NOT the
#     Fed-Watcher `backend.main:app`). Match precisely so we never kill fed.
if (-not $restarted) {
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -match 'app\.main:app' -and $_.CommandLine -notmatch 'backend\.main:app' }
        # Derive the port the app is actually serving on, if we can.
        $runPort = $Port
        foreach ($pr in $procs) {
            if ($pr.CommandLine -match '--port\s+(\d+)') { $runPort = [int]$Matches[1] }
        }
        if ($procs) {
            Write-Log "bare uvicorn krw process(es) found on port $runPort — stopping."
            foreach ($pr in $procs) {
                try { Stop-Process -Id $pr.ProcessId -Force -ErrorAction Stop; Write-Log "  stopped PID $($pr.ProcessId)" }
                catch { Write-Log "  PID $($pr.ProcessId) already gone" }
            }
            Start-Sleep -Seconds 3
        } else {
            Write-Log "no running krw uvicorn process found; launching a fresh one on port $runPort."
        }
        # (Re)launch krw-watcher from its own directory, detached, logs redirected.
        $job = Start-Process -FilePath "python" `
            -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $runPort" `
            -WorkingDirectory "$ProjectDir\krw-watcher" -PassThru `
            -RedirectStandardOutput "$ProjectDir\logs\krw.log" `
            -RedirectStandardError  "$ProjectDir\logs\krw_err.log"
        Write-Log "launched krw-watcher PID $($job.Id) on port $runPort"
        $Port = $runPort
        $restarted = $true
    } catch { Write-Log "  bare-process restart failed: $_" }
}

# 2c. Neither detected — the reset tree will take effect on the next boot.
if (-not $restarted) {
    Write-Log "No running krw-watcher (Docker or bare) detected. Code is reset to master;"
    Write-Log "it will take effect on the next server start (scheduler/boot_server.ps1 or reboot)."
    exit 0
}

# ── 3. Verify the restart actually came back healthy ────────────────────────
if (Test-KrwHealth $Port) {
    Write-Log "krw-watcher healthy on port $Port after sync. Done."
    exit 0
} else {
    Write-Log "WARNING: krw-watcher did not return healthy within ~90s after restart — check logs\krw_err.log"
    exit 1
}
