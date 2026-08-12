$ErrorActionPreference = "Stop"
$reviewerRoot = "E:\QuantLLMBot\apps\qwen_trade_software\backend"
$pythonw = "C:\ProgramData\Miniconda3\pythonw.exe"
$runtime = Join-Path $reviewerRoot "software_runtime.py"
$starterLog = Join-Path $reviewerRoot "logs\start-reviewer.log"
$dashboardHealth = "http://127.0.0.1:48632/snapshot"

function Write-StarterLog([string]$Message) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $starterLog) | Out-Null
        Add-Content -LiteralPath $starterLog -Value $line -ErrorAction SilentlyContinue
    } catch {
        # best-effort only
    }
}

function Test-SoftwareRunning {
    # Prefer dashboard health: Win32_Process.CommandLine is often blank without elevation.
    try {
        $response = Invoke-WebRequest -Uri $dashboardHealth -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            return $true
        }
    } catch {
        # not up yet
    }

    try {
        $listening = Get-NetTCPConnection -LocalPort 48632 -State Listen -ErrorAction SilentlyContinue
        if ($listening) {
            return $true
        }
    } catch {
        # cmdlet may be unavailable
    }

    $byCommandLine = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -eq "pythonw.exe" -or $_.Name -eq "python.exe") -and
            $_.CommandLine -like "*software_runtime.py*"
        }
    if ($byCommandLine) {
        return $true
    }

    return $false
}

if (Test-SoftwareRunning) {
    Write-StarterLog "already running (dashboard/port healthy)"
} else {
    Write-StarterLog "starting software_runtime.py"
    Start-Process -FilePath $pythonw -ArgumentList "`"$runtime`"" -WorkingDirectory $reviewerRoot -WindowStyle Hidden
}
