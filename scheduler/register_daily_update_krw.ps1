# Registers the daily morning repair check as a Windows Scheduled Task at
# 07:45 KST — right after the app's own ~07:30 morning cycle, so it only
# repairs mornings the internal schedule missed.
# Run ONCE in an elevated (Administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_update_krw.ps1
#
# -StartWhenAvailable makes a missed run (PC asleep / powered off) fire as
# soon as the machine is back — "if it can't run on time, run ASAP".

$ProjectDir = "C:\Users\andul\fed-watcher"
$ScriptPath = "$ProjectDir\scheduler\daily_update_krw.ps1"
$TaskName   = "KRW-Watcher Daily 8AM Update"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At 07:45

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Wakes krw-watcher and runs the daily briefing + forecast cycle. Missed runs fire on next boot/wake."

Write-Host "Registered '$TaskName' — daily 07:45, missed runs fire ASAP on wake."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName '$TaskName'"
