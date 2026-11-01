@echo off
rem ===========================================================================
rem  Test-Days.bat - day-by-day PLATFORM test of the whole trading system.
rem
rem  Runs October 2026 one trading day at a time through the live pipeline
rem  (structure engine -> strategy -> Bonsai 2 27B -> contract -> executor ->
rem  paper broker -> journal) on the bars stored in the database, and checks
rem  every day: data, crashes, model answers + latency vs the entry window,
rem  prompt budget, trading rules, executor, open positions.
rem
rem  Needs: the database (Docker), and the model running (Start-LLM.bat).
rem  Without the model:  Test-Days.bat stub     (platform only, fake answers)
rem  Other period:       Test-Days.bat llm 2026-09-01 2026-10-01
rem
rem  Reports: runs\daytest\<date-time>\summary.md (+ one JSON per day and
rem  decisions.jsonl with every raw model answer).
rem ===========================================================================
setlocal
cd /d "%~dp0backend"
set "PY=C:\ProgramData\Miniconda3\python.exe"
if not exist "%PY%" set "PY=python"
set "LANE=%~1"
if "%LANE%"=="" set "LANE=llm"
set "FROM=%~2"
if "%FROM%"=="" set "FROM=2026-10-01"
set "TO=%~3"
if "%TO%"=="" set "TO=2026-11-01"
"%PY%" -m trading.daytest --db --from %FROM% --to %TO% --lane %LANE%
pause
