@echo off
rem Restart QuantLLM: stop every running copy, then start it again.
rem Stops (1) the QuantLLM console windows, (2) anything still listening on
rem port 8765, (3) any python running "quantllm serve". Then runs Start-QuantLLM.bat.
title QuantLLM - restarting
cd /d "%~dp0"

echo Stopping QuantLLM...
taskkill /FI "WINDOWTITLE eq QuantLLM - market structure*" /T /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue };" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'quantllm' -and $_.CommandLine -match 'serve' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

rem give Windows a moment to release the port
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
  echo Port 8765 is still in use by another program. Close it and run this again.
  pause
  exit /b 1
)

echo Starting QuantLLM...
call "%~dp0Start-QuantLLM.bat"
