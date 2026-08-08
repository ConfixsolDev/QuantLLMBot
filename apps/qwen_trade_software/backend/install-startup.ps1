# Register the Qwen trading software to start automatically at Windows logon.
# Run once from PowerShell. Admin is optional for the current user's logon task.

$ErrorActionPreference = "Stop"

$TaskName = "QuantLLMBot - Qwen Reviewer"
$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $Backend "start-reviewer.ps1"

if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "Missing start script: $StartScript"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

# Delay 45s after logon so Windows, MT5, Ollama, and network are ready.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT45S"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Updating existing scheduled task: $TaskName" -ForegroundColor Yellow
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings | Out-Null
} else {
    Write-Host "Creating scheduled task: $TaskName" -ForegroundColor Yellow
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Start GoldFlow/Qwen trading software (reviewer, cache, paper runner) at Windows logon." | Out-Null
}

Write-Host ""
Write-Host "Startup task installed." -ForegroundColor Green
Write-Host "  Task name : $TaskName"
Write-Host "  Trigger   : At logon for $env:USERNAME (45 second delay)"
Write-Host "  Starts    : $StartScript"
Write-Host ""
Write-Host "Test now with:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Remove with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$Backend\uninstall-startup.ps1`""
