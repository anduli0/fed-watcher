# bootstrap_pc.ps1 — one-time PC setup for full auto-sync with the cloud.
#
# Run ONCE in an elevated (Administrator) PowerShell. After this, the PC keeps
# itself in sync with origin/master every morning (07:45 KST) and on every
# boot, with no further manual steps — a push to master reaches the PC and the
# Render service alike.
#
#   cd C:\Users\andul\fed-watcher
#   git fetch origin master; git reset --hard origin/master
#   powershell -ExecutionPolicy Bypass -File scheduler\bootstrap_pc.ps1
#
# (The two git lines pull THIS script and its siblings onto the PC first — the
# only step that cannot be automated from the cloud, since the machine must
# fetch the auto-updater once before it can update itself.)

param(
    [string]$ProjectDir = "C:\Users\andul\fed-watcher"
)

$ErrorActionPreference = "Continue"
Write-Host "=== krw-watcher PC bootstrap ===" -ForegroundColor Cyan

# 1. Make sure we're on the latest master (idempotent if already pulled).
Push-Location $ProjectDir
try {
    git fetch origin master --quiet
    git reset --hard origin/master
    Write-Host "on master: $(git rev-parse --short HEAD)"
} catch {
    Write-Host "WARNING: git sync failed: $_" -ForegroundColor Yellow
} finally { Pop-Location }

# 2. Register the daily 07:45 KST self-updating morning task.
$reg = "$ProjectDir\scheduler\register_daily_update_krw.ps1"
if (Test-Path $reg) {
    Write-Host "`nRegistering daily task..." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $reg
} else {
    Write-Host "register_daily_update_krw.ps1 missing — did the pull succeed?" -ForegroundColor Yellow
}

# 3. Run the sync now so the running app restarts on the new code immediately.
$sync = "$ProjectDir\scheduler\sync_krw.ps1"
if (Test-Path $sync) {
    Write-Host "`nSyncing + restarting krw-watcher now..." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $sync
}

# 4. Kick the morning update once so today's report is regenerated in the new
#    format right away (idempotent — skips anything already fresh).
Write-Host "`nRunning today's update..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName "KRW-Watcher Daily 8AM Update" -ErrorAction SilentlyContinue

Start-Sleep -Seconds 5
Write-Host "`n=== Done. Live logs: ===" -ForegroundColor Green
Write-Host "  $ProjectDir\logs\sync_krw.log"
Write-Host "  $ProjectDir\logs\daily_update_krw.log"
Write-Host "`nFrom now on the PC self-syncs at 07:45 KST and on every boot." -ForegroundColor Green
