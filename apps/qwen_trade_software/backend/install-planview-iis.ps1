# Requires Administrator PowerShell.
# Builds GoldFlow Plan View and deploys it as the only local website.
# Retires Default Web Site and the legacy GoldFlow Desk site.

$ErrorActionPreference = "Stop"
$SiteName = "GoldFlowPlanView"
$SiteRoot = "C:\inetpub\GoldFlowPlanView"
$LegacyDeskRoot = "C:\inetpub\GoldFlowDesk"
$PlanViewDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\planview"

Write-Host "=== Deploy GoldFlow Plan View (sole website) ===" -ForegroundColor Cyan

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
        throw "Build did not produce out/ - check next.config.ts output: export"
    }
    Write-Host "Replacing files at $SiteRoot..." -ForegroundColor Yellow
    if (Test-Path $SiteRoot) {
        Get-ChildItem -Path $SiteRoot -Force | Remove-Item -Recurse -Force
    } else {
        New-Item -ItemType Directory -Force -Path $SiteRoot | Out-Null
    }
    Copy-Item -Path (Join-Path $OutDir "*") -Destination $SiteRoot -Recurse -Force
} finally {
    Pop-Location
}

Import-Module WebAdministration -ErrorAction Stop

function Remove-SiteIfPresent([string]$Name) {
    $site = Get-Website -Name $Name -ErrorAction SilentlyContinue
    if (-not $site) { return }
    Write-Host "Removing retired IIS site '$Name'..." -ForegroundColor Yellow
    if ($site.State -eq "Started") {
        Stop-Website -Name $Name
    }
    Remove-Website -Name $Name
}

# Stock IIS welcome page and legacy Desk UI are no longer used.
Remove-SiteIfPresent "Default Web Site"
Remove-SiteIfPresent "GoldFlowDesk"
if (Test-Path $LegacyDeskRoot) {
    Write-Host "Removing legacy Desk deploy folder $LegacyDeskRoot..." -ForegroundColor Yellow
    Remove-Item -Path $LegacyDeskRoot -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Get-Website -Name $SiteName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating IIS site $SiteName on port 8088..." -ForegroundColor Yellow
    New-Website -Name $SiteName -PhysicalPath $SiteRoot -Port 8088 | Out-Null
} else {
    Write-Host "Updating existing IIS site $SiteName..." -ForegroundColor Yellow
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $SiteRoot
}

# Also bind port 80 so http://127.0.0.1/ opens Plan View.
$hasPort80 = Get-WebBinding -Name $SiteName -ErrorAction SilentlyContinue |
    Where-Object { $_.Protocol -eq "http" -and $_.BindingInformation -match ':80:' }
if (-not $hasPort80) {
    Write-Host "Binding $SiteName to port 80..." -ForegroundColor Yellow
    New-WebBinding -Name $SiteName -Protocol http -Port 80 -IPAddress "*"
}

if ((Get-Website -Name $SiteName).State -ne "Started") {
    Start-Website -Name $SiteName
}

Start-Service W3SVC
Write-Host "Plan View deployed." -ForegroundColor Green
Write-Host "  http://127.0.0.1:8088/" -ForegroundColor Green
Write-Host "  http://127.0.0.1/" -ForegroundColor Green
Get-Website | Select-Object Name, State, PhysicalPath | Format-Table -AutoSize
