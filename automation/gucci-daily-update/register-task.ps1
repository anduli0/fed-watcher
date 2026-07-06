# Gucci Intelligence PC 폴백 — 윈도우 작업 스케줄러 등록
#
# 관리자 권한 PowerShell에서 1회 실행:
#   powershell -ExecutionPolicy Bypass -File .\register-task.ps1
#
# 기본 스케줄: 매일 09:00 (클라우드 정기 06:50 시작 + 보정 08:05가 모두 실패했을 때만 실제 동작)
# -StartWhenAvailable 덕분에 09:00에 PC가 꺼져 있었으면 켜지는 즉시 실행된다("되는대로 바로").

param(
    [string]$Time = "09:00"
)

$ScriptPath = Join-Path $PSScriptRoot "run-daily-update.ps1"
if (-not (Test-Path $ScriptPath)) { throw "run-daily-update.ps1 을 찾을 수 없습니다: $ScriptPath" }

$Action   = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Trigger  = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "GucciIntelDailyUpdate" `
    -Action $Action -Trigger $Trigger -Settings $Settings -Force

Write-Host "등록 완료: 'GucciIntelDailyUpdate' — 매일 $Time (놓치면 PC 켜질 때 즉시 실행)"
Write-Host "해제하려면: Unregister-ScheduledTask -TaskName GucciIntelDailyUpdate -Confirm:`$false"
