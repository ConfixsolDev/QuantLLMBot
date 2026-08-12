# Register the Qwen trading software to start when Windows boots / the user
# logs on, and keep itself running via a periodic watchdog.

$ErrorActionPreference = "Stop"

$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $Backend "start-reviewer.ps1"
$MainTaskName = "QuantLLMBot - Qwen Reviewer"
$WatchdogTaskName = "QuantLLMBot - Qwen Watchdog"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$StartupShortcut = Join-Path $StartupFolder "QuantLLMBot Qwen Reviewer.lnk"

if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "Missing start script: $StartScript"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logonTrigger.Delay = "PT45S"

$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$startupTrigger.Delay = "PT90S"

# Prefer boot + logon; AtStartup often needs an elevated PowerShell.
$mainTriggers = @($startupTrigger, $logonTrigger)
$usedStartupTrigger = $true

function Set-OrRegisterMainTask {
    param([array]$Triggers)
    $existing = Get-ScheduledTask -TaskName $MainTaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Updating existing scheduled task: $MainTaskName" -ForegroundColor Yellow
        Set-ScheduledTask `
            -TaskName $MainTaskName `
            -Action $action `
            -Trigger $Triggers `
            -Settings $settings `
            -Principal $principal | Out-Null
    } else {
        Write-Host "Creating scheduled task: $MainTaskName" -ForegroundColor Yellow
        Register-ScheduledTask `
            -TaskName $MainTaskName `
            -Action $action `
            -Trigger $Triggers `
            -Settings $settings `
            -Principal $principal `
            -Description "Start GoldFlow/Qwen trading software at Windows startup and user logon." | Out-Null
    }
}

try {
    Set-OrRegisterMainTask -Triggers $mainTriggers
} catch {
    $usedStartupTrigger = $false
    Write-Host "At-startup trigger needs Administrator; using logon trigger instead." -ForegroundColor Yellow
    Write-Host ("  ({0})" -f $_.Exception.Message) -ForegroundColor DarkYellow
    Set-OrRegisterMainTask -Triggers @($logonTrigger)
}

# Watchdog: every 5 minutes; start-reviewer.ps1 no-ops if already healthy.
$watchdogTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$existingWatchdog = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
if ($existingWatchdog) {
    Write-Host "Updating existing scheduled task: $WatchdogTaskName" -ForegroundColor Yellow
    Set-ScheduledTask `
        -TaskName $WatchdogTaskName `
        -Action $action `
        -Trigger $watchdogTrigger `
        -Settings $settings `
        -Principal $principal | Out-Null
} else {
    Write-Host "Creating scheduled task: $WatchdogTaskName" -ForegroundColor Yellow
    Register-ScheduledTask `
        -TaskName $WatchdogTaskName `
        -Action $action `
        -Trigger $watchdogTrigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Every 5 minutes: start GoldFlow/Qwen if it is not already healthy." | Out-Null
}

# Classic Windows Startup folder shortcut (no admin required).
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($StartupShortcut)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$shortcut.WorkingDirectory = $Backend
$shortcut.WindowStyle = 7
$shortcut.Description = "Start QuantLLMBot / Qwen trading software"
$shortcut.Save()
Write-Host "Startup folder shortcut: $StartupShortcut" -ForegroundColor Yellow

Write-Host ""
Write-Host "Startup configured." -ForegroundColor Green
if ($usedStartupTrigger) {
    Write-Host "  Main task     : $MainTaskName (at system startup +90s, at logon +45s)"
} else {
    Write-Host "  Main task     : $MainTaskName (at logon +45s)"
    Write-Host "  Tip           : re-run this script from an Administrator PowerShell to also bind At Startup."
}
Write-Host "  Watchdog task : $WatchdogTaskName (every 5 minutes)"
Write-Host "  Startup folder: $StartupShortcut"
Write-Host "  Starts        : $StartScript"
Write-Host ""
Write-Host "Test now with:"
Write-Host "  Start-ScheduledTask -TaskName '$MainTaskName'"
Write-Host ""
Write-Host "Remove with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$Backend\uninstall-startup.ps1`""
