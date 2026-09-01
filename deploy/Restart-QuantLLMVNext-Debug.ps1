param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [double]$IntervalSeconds = 60,
    [double]$QwenTimeoutSeconds = 120,
    [int]$MaxCycles = 0,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
if ($IntervalSeconds -le 0 -or $QwenTimeoutSeconds -le 0 -or $MaxCycles -lt 0) {
    throw 'Restart parameters must be positive (MaxCycles may be zero).'
}

$appRoot = Join-Path $ProjectRoot 'apps/qwen_trade_software'
$python = Join-Path $appRoot '.venv/Scripts/python.exe'
$runner = Join-Path $appRoot 'vnext/tools/run_debug_service.py'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $runner)) {
    throw 'The vNext debug runner or its application Python environment is missing.'
}

# Stop only the launcher and child processes for this exact vNext runner.
$launchers = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.ExecutablePath -eq $python -and $_.CommandLine -and $_.CommandLine.Contains($runner)
})
$launcherIds = @($launchers | ForEach-Object { $_.ProcessId })
$children = @(Get-CimInstance Win32_Process | Where-Object {
    $launcherIds -contains $_.ParentProcessId -and $_.CommandLine -and $_.CommandLine.Contains($runner)
})
foreach ($process in @($children) + @($launchers)) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    $remaining = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
        $_.ExecutablePath -eq $python -and $_.CommandLine -and $_.CommandLine.Contains($runner)
    })
    if ($remaining.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)
if ($remaining.Count -ne 0) { throw 'The existing vNext debug launcher did not stop.' }

# Bring V2 dependencies to a healthy state before clearing this worker's stale lease.
& (Join-Path $PSScriptRoot 'Start-QuantLLMVNext.ps1') -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'V2 preflight failed; the debug worker was not restarted.' }
docker exec deploy-redis-1 redis-cli DEL qwen:vnext:debug-service:lease | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Unable to clear the vNext debug-service lease.' }

$arguments = @($runner, '--interval-seconds', $IntervalSeconds,
    '--qwen-timeout-seconds', $QwenTimeoutSeconds, '--max-cycles', $MaxCycles)
if ($Foreground) {
    & $python @arguments
    exit $LASTEXITCODE
}

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
Write-Host "vNext debug service restarted with PID $($process.Id). Broker submission remains disabled."
