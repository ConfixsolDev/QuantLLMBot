# Requires Administrator PowerShell.
# Builds the Next.js plan view and deploys static export to IIS on port 8088.

$ErrorActionPreference = "Stop"
$SiteName = "GoldFlowPlanView"
$SiteRoot = "C:\inetpub\GoldFlowPlanView"
$PlanViewDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\planview"

Write-Host "=== Deploy GoldFlow Plan View to IIS ===" -ForegroundColor Cyan

Push-Location $PlanViewDir
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
        npm install
    }
    Write-Host "Building static export..." -ForegroundColor Yellow
    npm run build
    $OutDir = Join-Path $PlanViewDir "out"
    if (-not (Test-Path $OutDir)) {
        throw "Build did not produce out/ — check next.config.ts output: export"
    }
    Write-Host "Copying to $SiteRoot..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $SiteRoot | Out-Null
    Copy-Item -Path (Join-Path $OutDir "*") -Destination $SiteRoot -Recurse -Force
} finally {
    Pop-Location
}

Import-Module WebAdministration -ErrorAction Stop

if (-not (Get-Website -Name $SiteName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating IIS site $SiteName on port 8088..." -ForegroundColor Yellow
    New-Website -Name $SiteName -PhysicalPath $SiteRoot -Port 8088 | Out-Null
} else {
    Write-Host "Updating existing IIS site $SiteName..." -ForegroundColor Yellow
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $SiteRoot
}

Start-Service W3SVC
Write-Host "Plan View deployed. Test: http://127.0.0.1:8088/" -ForegroundColor Green
Write-Host "Dev mode: cd planview && npm run dev  (http://localhost:3000)" -ForegroundColor Green
