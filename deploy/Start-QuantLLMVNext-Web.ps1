param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [int]$Port = 8090,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be between 1 and 65535.' }

& (Join-Path $PSScriptRoot 'Enable-QuantLLMStorage.ps1') -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'V2 storage acceptance failed; web dashboard was not started.' }

$appRoot = Join-Path $ProjectRoot 'apps/qwen_trade_software'
$python = Join-Path $appRoot '.venv/Scripts/python.exe'
$runner = Join-Path $appRoot 'vnext/tools/run_web_service.py'
if (-not (Test-Path -LiteralPath $runner)) { throw "vNext web runner not found: $runner" }
$arguments = @($runner, '--host', '127.0.0.1', '--port', $Port)

if ($Foreground) {
    & $python @arguments
    exit $LASTEXITCODE
}

$existing = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($runner) -and $_.CommandLine.Contains("--port $Port")
})
if ($existing.Count -gt 0) {
    Write-Host "vNext web dashboard is already running at http://127.0.0.1:$Port/"
    exit 0
}

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 750
if ($process.HasExited) {
    throw "vNext web dashboard failed to start. Check whether localhost port $Port is already in use."
}
Write-Host "vNext read-only web dashboard launched with PID $($process.Id) at http://127.0.0.1:$Port/"
