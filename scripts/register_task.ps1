# Register daily 09:30 fetch task (runs late if PC was off at 09:30).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 misreads BOM-less UTF-8 Chinese).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$py = (Get-Command python -ErrorAction Stop).Source
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }   # fallback: python.exe (shows a console window)

$Action   = New-ScheduledTaskAction -Execute $pyw -Argument "run_fetch.py" -WorkingDirectory $Root
$Trigger  = New-ScheduledTaskTrigger -Daily -At "09:30"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "JobAggregator-Daily" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "OK: JobAggregator-Daily registered (daily 09:30, via $pyw)"
Write-Host "Test run now:  schtasks /Run /TN JobAggregator-Daily"
