@echo off
rem Start QuantLLM: the trading model (Start-LLM.bat, own window) + the app
rem (database, MT5, structure engine, website http://127.0.0.1:8765/).
rem Autostart at Windows logon: run Install-Autostart.bat once.
setlocal
title QuantLLM - market structure
cd /d "%~dp0"

rem ---- Python: the one that already has MetaTrader5 (change if yours is elsewhere)
set "PY=C:\ProgramData\Miniconda3\python.exe"
if not exist "%PY%" set "PY=python"

rem ---- Database connection (existing TimescaleDB). Set once with:
rem      setx QUANTLLM_DB_DSN "postgresql://USER:PASSWORD@127.0.0.1:5432/DBNAME"
if "%QUANTLLM_DB_DSN%%QWEN_TIMESCALE_DSN%"=="" (
  echo No database connection. Run once:  setx QUANTLLM_DB_DSN "postgresql://USER:PASSWORD@127.0.0.1:5432/DBNAME"
  echo then open a new window and start again.
  pause
  exit /b 1
)

rem ---- Python packages (only installs when missing)
"%PY%" -c "import psycopg, MetaTrader5" 2>nul || "%PY%" -m pip install -r requirements.txt

rem ---- Website: built once (needs Node.js), then served by the backend
if not exist "web\out\index.html" (
  echo Building the website once...
  pushd web
  call npm install --no-audit --no-fund
  call npm run build
  popd
)

rem ---- The trading model (Bonsai 2 27B on llama-server, port 8080), in its own
rem      minimised window - only if it is installed (Setup-LLM.bat) and not already running
if exist "llm-runtime\bin\llama-server.exe" (
  powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
  if errorlevel 1 (
    echo [ok] trading model already running on port 8080
  ) else (
    echo Starting the trading model ^(Start-LLM.bat^) in its own window...
    start "Bonsai 2 27B - trading model" /min cmd /c ""%~dp0Start-LLM.bat""
  )
) else (
  echo [info] trading model not installed - run Setup-LLM.bat once to enable trading decisions
)

echo Opening http://127.0.0.1:8765/  (the page fills in once history is loaded)
start "" http://127.0.0.1:8765/
cd backend
"%PY%" -m quantllm serve
pause
