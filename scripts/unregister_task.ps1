# Remove the daily fetch task.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\unregister_task.ps1
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 misreads BOM-less UTF-8 Chinese).

Unregister-ScheduledTask -TaskName "JobAggregator-Daily" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "OK: JobAggregator-Daily removed"
