param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$compose = Join-Path $PSScriptRoot 'docker-compose.storage.yml'
$backend = Join-Path $ProjectRoot 'apps/qwen_trade_software/backend'
$python = Join-Path $backend '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { throw "Backend Python not found: $python" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required. Install Docker Desktop with Linux containers first.' }

$envFile = Join-Path $PSScriptRoot '.env'
$composeArgs = @('-f', $compose)
if (Test-Path $envFile) { $composeArgs += @('--env-file', $envFile) }
$dbPassword = $env:POSTGRES_PASSWORD
$neo4jPassword = $env:NEO4J_PASSWORD
if (-not $dbPassword -and (Test-Path $envFile)) {
    $passwordLine = Get-Content -LiteralPath $envFile | Where-Object {
        $_ -match '^\s*POSTGRES_PASSWORD\s*=\s*(.+?)\s*$'
    } | Select-Object -First 1
    if ($passwordLine) { $dbPassword = $Matches[1] }
}
if (-not $env:QWEN_TIMESCALE_DSN -and -not $dbPassword) {
    throw 'Set POSTGRES_PASSWORD (or POSTGRES_PASSWORD in deploy/.env) before activation.'
}
if (-not $neo4jPassword -and (Test-Path $envFile)) {
    $neo4jLine = Get-Content -LiteralPath $envFile | Where-Object {
        $_ -match '^\s*NEO4J_PASSWORD\s*=\s*(.+?)\s*$'
    } | Select-Object -First 1
    if ($neo4jLine) { $neo4jPassword = $Matches[1] }
}
if (-not $neo4jPassword) { throw 'Set NEO4J_PASSWORD (or NEO4J_PASSWORD in deploy/.env) before activation.' }
if ($dbPassword) { $env:POSTGRES_PASSWORD = $dbPassword }
$env:NEO4J_PASSWORD = $neo4jPassword
docker compose @composeArgs up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Storage services failed to start.' }

$env:QWEN_TIMESCALE_DSN = if ($env:QWEN_TIMESCALE_DSN) { $env:QWEN_TIMESCALE_DSN } else { "postgresql://quantllm:$dbPassword@127.0.0.1:5432/quantllm" }
$env:QWEN_REDIS_URL = if ($env:QWEN_REDIS_URL) { $env:QWEN_REDIS_URL } else { 'redis://127.0.0.1:6379/0' }
$env:QWEN_NEO4J_URI = if ($env:QWEN_NEO4J_URI) { $env:QWEN_NEO4J_URI } else { 'bolt://127.0.0.1:7687' }
$env:QWEN_NEO4J_USER = if ($env:QWEN_NEO4J_USER) { $env:QWEN_NEO4J_USER } else { 'neo4j' }
$env:QWEN_NEO4J_PASSWORD = $neo4jPassword
& $python (Join-Path $ProjectRoot 'apps/qwen_trade_software/vnext/tools/storage_acceptance.py')
if ($LASTEXITCODE -ne 0) { throw 'Storage acceptance gate failed; live backend variables were not validated.' }
Write-Host 'QuantLLM storage is ready for this PowerShell session.'
Write-Host "QWEN_REDIS_URL=$env:QWEN_REDIS_URL"
