<#
    Restarts the full QwenTradeSoftware supervised chain AND the MT5 terminal
    connection it depends on, in one step.

    v2 (2026-08-07): the first version of this script silently swallowed
    Stop-Process permission errors (-ErrorAction SilentlyContinue on the kill
    step meant an Access Denied failure looked identical to a successful
    kill in the console output). That let the old software_runtime.py
    process survive three separate restart attempts while the script kept
    reporting a clean run. This version reports every kill failure
    explicitly instead of proceeding on a false "stopped everything"
    assumption. It also restarts the MT5 terminal itself -- software_runtime.py
    only launches MT5 if tasklist doesn't see terminal64.exe running at all,
    so a terminal that's open but has lost its IPC session (the "IPC send
    failed" errors seen in market-context-cache.log) never gets relaunched on
    its own. Closing and reopening the terminal does not touch open
    positions -- those live on the broker server; only the local API/UI
    session resets.

    Safe to run with an open paper position.

    Usage: right-click -> Run with PowerShell, or from a PowerShell prompt:
        & "D:\QuantLLMBot\apps\qwen_trade_software\backend\restart-software.ps1"

    If any kill step reports FAILED, re-run this from an Administrator
    PowerShell window (right-click PowerShell -> Run as Administrator).
#>

$ErrorActionPreference = "Stop"

$backendRoot = "E:\QuantLLMBot\apps\qwen_trade_software\backend"
$starter = Join-Path $backendRoot "start-reviewer.ps1"
$dashboardHealth = "http://127.0.0.1:48632/snapshot"

$pyPattern = "software_runtime\.py|reviewer\.py|trade_management\.py|market_context_cache\.py|paper_runner\.py|session_planner\.py"

function Stop-MatchingProcesses {
    param([string]$Label, [scriptblock]$Filter)

    $targets = Get-CimInstance Win32_Process | Where-Object $Filter
    if (-not $targets) {
        Write-Host "  $Label -- nothing was running."
        return $true
    }

    $allStopped = $true
    foreach ($proc in $targets) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host ("  stopped pid {0} ({1})" -f $proc.ProcessId, $proc.Name)
        } catch {
            $allStopped = $false
            Write-Host ("  FAILED to stop pid {0} ({1}): {2}" -f $proc.ProcessId, $proc.Name, $_.Exception.Message) -ForegroundColor Red
        }
    }
    return $allStopped
}

Write-Host "Stopping the QwenTradeSoftware python chain..."
$pythonOk = Stop-MatchingProcesses -Label "python chain" -Filter { $_.CommandLine -match $pyPattern }

Write-Host "Stopping the MT5 terminal (fixes a stuck IPC session; open positions are unaffected -- they live on the broker)..."
$mt5Ok = Stop-MatchingProcesses -Label "MT5 terminal" -Filter { $_.Name -eq "terminal64.exe" }

if (-not ($pythonOk -and $mt5Ok)) {
    Write-Host ""
    Write-Host "One or more processes could not be stopped (see FAILED lines above)." -ForegroundColor Yellow
    Write-Host "This is almost always a permissions mismatch -- re-run this script from an" -ForegroundColor Yellow
    Write-Host "Administrator PowerShell window (right-click PowerShell -> Run as Administrator)" -ForegroundColor Yellow
    Write-Host "and try again. Continuing anyway, but the relaunch below may just report" -ForegroundColor Yellow
    Write-Host "'already running' again if the old process survived." -ForegroundColor Yellow
}

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Relaunching via start-reviewer.ps1 (this also restarts MT5, since it's no longer running)..."
& $starter

Write-Host "Waiting for the dashboard to come back up (MT5 + Ollama + IIS checks can take a couple minutes)..."
$deadline = (Get-Date).AddSeconds(150)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $dashboardHealth -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        # not up yet -- keep polling until the deadline
    }
    Start-Sleep -Seconds 3
}

Write-Host ""
if ($healthy) {
    Write-Host "Dashboard is responding." -ForegroundColor Green
} else {
    Write-Host "Dashboard did not come back within 150s -- check logs\software-runtime.log." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Current chain (check CreationDate -- it should be within the last minute or two):"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pyPattern -or $_.Name -eq "terminal64.exe" } |
    Select-Object ProcessId, Name, CreationDate | Format-Table -AutoSize
