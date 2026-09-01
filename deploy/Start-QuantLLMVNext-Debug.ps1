param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [double]$IntervalSeconds = 60,
    [double]$QwenTimeoutSeconds = 120,
    [int]$MaxCycles = 0,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Start-QuantLLMVNext.ps1') -ProjectRoot $ProjectRoot

$appRoot = Join-Path $ProjectRoot 'apps/qwen_trade_software'
$python = Join-Path $appRoot '.venv/Scripts/python.exe'
$runner = Join-Path $appRoot 'vnext/tools/run_debug_service.py'
if (-not (Test-Path -LiteralPath $runner)) { throw "vNext debug runner not found: $runner" }
$arguments = @($runner, '--interval-seconds', $IntervalSeconds,
    '--qwen-timeout-seconds', $QwenTimeoutSeconds, '--max-cycles', $MaxCycles)

if ($Foreground) {
    & $python @arguments
    exit $LASTEXITCODE
}

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
Write-Host "vNext debug service launched with PID $($process.Id). Broker submission is disabled."
