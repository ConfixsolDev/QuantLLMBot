# Remove the Qwen trading software Windows logon scheduled task.

$ErrorActionPreference = "Stop"
$TaskName = "QuantLLMBot - Qwen Reviewer"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Task not found: $TaskName" -ForegroundColor Yellow
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed scheduled task: $TaskName" -ForegroundColor Green
