# Enable IIS and deploy the GoldFlow Desk website for the Qwen runtime.
# Requires Administrator PowerShell.

$ErrorActionPreference = "Stop"
$SiteName = "GoldFlowDesk"
$SiteRoot = "C:\inetpub\GoldFlowDesk"
$BackendRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeskRoot = Join-Path $BackendRoot "..\desk"
$Source = Join-Path $BackendRoot "..\website"

Write-Host "=== Deploy GoldFlow Desk website to IIS ===" -ForegroundColor Cyan

if (Test-Path (Join-Path $DeskRoot "package.json")) {
    Write-Host "Building GoldFlow Desk from source..." -ForegroundColor Yellow
    Push-Location $DeskRoot
    if (-not (Test-Path "node_modules")) {
        npm install
    }
    npm run build
    Pop-Location
} else {
    Write-Host "Desk source not found; deploying existing website bundle." -ForegroundColor Yellow
}

$features = @(
    "IIS-WebServerRole",
    "IIS-WebServer",
    "IIS-CommonHttpFeatures",
    "IIS-StaticContent",
    "IIS-DefaultDocument",
    "IIS-HttpErrors",
    "IIS-HttpLogging",
    "IIS-RequestFiltering"
)

Write-Host "Enabling IIS features..." -ForegroundColor Yellow
Enable-WindowsOptionalFeature -Online -FeatureName $features -All -NoRestart | Out-Null

Write-Host "Copying website files to $SiteRoot..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $SiteRoot | Out-Null
Copy-Item -Path (Join-Path $Source "*") -Destination $SiteRoot -Recurse -Force

Import-Module WebAdministration -ErrorAction Stop

if (-not (Get-Website -Name $SiteName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating IIS site $SiteName on port 80..." -ForegroundColor Yellow
    New-Website -Name $SiteName -PhysicalPath $SiteRoot -Port 80 | Out-Null
} else {
    Write-Host "Updating existing IIS site $SiteName..." -ForegroundColor Yellow
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $SiteRoot
}

Start-Service W3SVC
Write-Host "IIS website deployed. Test: http://127.0.0.1/" -ForegroundColor Green
