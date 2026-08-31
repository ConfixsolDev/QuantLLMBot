param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$storage = Join-Path $PSScriptRoot 'Enable-QuantLLMStorage.ps1'
if (-not (Test-Path -LiteralPath $storage)) { throw "V2 storage bootstrap not found: $storage" }

# The V2 start boundary is deliberately gated. It starts no worker unless the
# three stores and the broker/ledger reconciliation preflight both pass.
& $storage -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'V2 storage acceptance failed.' }

$python = Join-Path $ProjectRoot 'apps/qwen_trade_software/backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Backend Python not found: $python" }
$env:PYTHONPATH = "$(Join-Path $ProjectRoot 'apps/qwen_trade_software');$(Join-Path $ProjectRoot 'apps/qwen_trade_software/backend')"
& $python (Join-Path $ProjectRoot 'apps/qwen_trade_software/vnext/tools/cutover_preflight.py')
if ($LASTEXITCODE -ne 0) { throw 'V2 cutover preflight failed; no V2 worker was started.' }
Write-Host 'V2 infrastructure and broker reconciliation preflight passed.'
