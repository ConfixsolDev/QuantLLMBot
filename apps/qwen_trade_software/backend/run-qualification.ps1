# Stop workers, run cache qualification, then restart the full software chain.
# Use when qualification must be rerun cleanly outside normal startup.

$ErrorActionPreference = "Stop"
$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$Restart = Join-Path $Backend "restart-software.ps1"

Write-Host "=== Qwen cache qualification ===" -ForegroundColor Cyan

$portPids = netstat -ano | Select-String "127\.0\.0\.1:(48631|48632|48633)\s" |
    ForEach-Object { if ($_ -match '\s(\d+)\s*$') { [int]$Matches[1] } }
$procIds = @($portPids) + @(
    Get-Process -Name pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like '*Miniconda3*' -or $_.Name -eq 'pythonw' } |
        Select-Object -ExpandProperty Id
) | Select-Object -Unique

foreach ($procId in $procIds) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "  stopped pid $procId"
    } catch {
        Write-Host "  could not stop pid ${procId}: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
Remove-Item (Join-Path $Backend "software-runtime.lock") -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$sw = [System.Diagnostics.Stopwatch]::StartNew()
& "C:\ProgramData\Miniconda3\python.exe" (Join-Path $Backend "cache_qualification_gate.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Qualification failed. Trading chain was not restarted." -ForegroundColor Red
    exit $LASTEXITCODE
}
$sw.Stop()
Write-Host "Qualification completed in $([math]::Round($sw.Elapsed.TotalSeconds, 1))s" -ForegroundColor Green

Write-Host "Restarting software..."
& $Restart
