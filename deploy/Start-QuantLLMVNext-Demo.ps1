param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [double]$IntervalSeconds = 1,
    [int]$MaxCycles = 0,
    [switch]$EnableDemoSubmissions,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
if (-not $EnableDemoSubmissions) {
    throw 'Refusing to start order submission. Re-run with -EnableDemoSubmissions after reviewing preflight.'
}
if ($IntervalSeconds -le 0 -or $MaxCycles -lt 0) {
    throw 'IntervalSeconds must be positive and MaxCycles may not be negative.'
}

# This imports the storage environment, validates all stores, and reconciles
# the strategy's exclusive magic namespace before a submission-capable worker
# may start. It launches no worker itself.
& (Join-Path $PSScriptRoot 'Start-QuantLLMVNext.ps1') -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'V2 preflight failed; the demo worker was not started.' }

$appRoot = Join-Path $ProjectRoot 'apps/qwen_trade_software'
$python = Join-Path $appRoot '.venv/Scripts/python.exe'
$runner = Join-Path $appRoot 'vnext/tools/run_demo_service.py'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $runner)) {
    throw 'The vNext demo runner or its application Python environment is missing.'
}

# The Python worker independently requires both this environment variable and
# its command-line switch, so an accidental direct launch cannot submit.
$env:QWEN_VNEXT_DEMO_SUBMISSIONS = '1'
$arguments = @($runner, '--enable-demo-submissions', '--interval-seconds', $IntervalSeconds,
    '--max-cycles', $MaxCycles)
if ($Foreground) {
    & $python @arguments
    exit $LASTEXITCODE
}

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
Write-Host "vNext demo worker launched with PID $($process.Id). It is restricted to demo accounts and magic 3101."
