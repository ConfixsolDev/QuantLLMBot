# Legacy entry point. GoldFlow Desk was retired; Plan View is the only website.
# Requires Administrator PowerShell.

$ErrorActionPreference = "Stop"
$PlanViewInstall = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "install-planview-iis.ps1"

Write-Host "GoldFlow Desk was removed. Deploying GoldFlow Plan View instead..." -ForegroundColor Yellow
& $PlanViewInstall
