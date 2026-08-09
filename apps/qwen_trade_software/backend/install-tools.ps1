# Install Python tooling required by the local Qwen trade software.
# Run in an elevated PowerShell if Miniconda is not already installed.

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$Miniconda = "C:\ProgramData\Miniconda3"
$Python = Join-Path $Miniconda "python.exe"
$Requirements = Join-Path $Backend "requirements.txt"
$Installer = Join-Path $env:TEMP "Miniconda3-latest-Windows-x86_64.exe"

Write-Host "=== Qwen software tool install ===" -ForegroundColor Cyan

if (-not (Test-Path $Python)) {
    Write-Host "Downloading Miniconda..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile $Installer
    Write-Host "Installing Miniconda to $Miniconda (admin prompt may appear)..." -ForegroundColor Yellow
    Start-Process -FilePath $Installer -ArgumentList @(
        "/InstallationType=AllUsers",
        "/RegisterPython=1",
        "/AddToPath=1",
        "/S",
        "/D=$Miniconda"
    ) -Wait -Verb RunAs
}

if (-not (Test-Path $Python)) {
    throw "Miniconda install failed or was cancelled."
}

Write-Host "Python: $(& $Python --version)" -ForegroundColor Green
Write-Host "Installing Python packages..." -ForegroundColor Yellow
& $Python -m pip install --upgrade pip
& $Python -m pip install -r $Requirements

Write-Host "Verifying imports..." -ForegroundColor Yellow
& $Python -c "import MetaTrader5 as mt5; print('MetaTrader5', mt5.__version__)"

Write-Host "Running cache self-test..." -ForegroundColor Yellow
& $Python (Join-Path $Backend "market_context_cache.py") --self-test

Write-Host ""
Write-Host "Done. Still required outside this script:" -ForegroundColor Cyan
Write-Host "  - Ollama with qwen-trading-v003:latest registered"
Write-Host "  - MetaTrader 5 terminal installed and logged in"
Write-Host "  - IIS + GoldFlowDesk website at C:\inetpub\GoldFlowDesk (for full runtime)"
Write-Host "Start the app with: powershell -ExecutionPolicy Bypass -File `"$Backend\start-reviewer.ps1`""
