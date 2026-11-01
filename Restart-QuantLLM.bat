@echo off
rem Restart QuantLLM: stop every running copy of the app AND the trading model,
rem then start both again (Start-QuantLLM.bat starts the model too).
rem Stops (1) the QuantLLM and model console windows, (2) anything listening on
rem port 8765 (app) or 8080 (model), (3) any python running "quantllm serve",
rem (4) llama-server.exe from this folder. Then runs Start-QuantLLM.bat.
title QuantLLM - restarting
cd /d "%~dp0"

echo Stopping QuantLLM and the trading model...
taskkill /FI "WINDOWTITLE eq QuantLLM - market structure*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Bonsai 2 27B - trading model*" /T /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-NetTCPConnection -LocalPort 8765,8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue };" ^
  "Get-Process llama-server -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '%~dp0*' } | Stop-Process -Force -ErrorAction SilentlyContinue;" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'quantllm' -and $_.CommandLine -match 'serve' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

rem give Windows a moment to release the port
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8765,8080 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
  echo Port 8765 or 8080 is still in use by another program. Close it and run this again.
  pause
  exit /b 1
)

echo Starting QuantLLM...
call "%~dp0Start-QuantLLM.bat"
