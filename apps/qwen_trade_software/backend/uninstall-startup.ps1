# Remove the Qwen trading software Windows startup entries.

$ErrorActionPreference = "Stop"
$TaskNames = @(
    "QuantLLMBot - Qwen Reviewer",
    "QuantLLMBot - Qwen Watchdog"
)
$StartupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "QuantLLMBot Qwen Reviewer.lnk"

foreach ($TaskName in $TaskNames) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "Task not found: $TaskName" -ForegroundColor Yellow
        continue
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName" -ForegroundColor Green
}

if (Test-Path -LiteralPath $StartupShortcut) {
    Remove-Item -LiteralPath $StartupShortcut -Force
    Write-Host "Removed Startup folder shortcut: $StartupShortcut" -ForegroundColor Green
} else {
    Write-Host "Startup shortcut not found: $StartupShortcut" -ForegroundColor Yellow
}
