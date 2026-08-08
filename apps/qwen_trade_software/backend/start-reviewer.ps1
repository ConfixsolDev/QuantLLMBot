$ErrorActionPreference = "Stop"
$reviewerRoot = "E:\QuantLLMBot\apps\qwen_trade_software\backend"
$pythonw = "C:\ProgramData\Miniconda3\pythonw.exe"
$runtime = Join-Path $reviewerRoot "software_runtime.py"

$runtimeRunning = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "pythonw.exe" -and
        $_.CommandLine -like "*software_runtime.py*"
    }

if (-not $runtimeRunning) {
    Start-Process -FilePath $pythonw -ArgumentList "`"$runtime`"" -WorkingDirectory $reviewerRoot -WindowStyle Hidden
}