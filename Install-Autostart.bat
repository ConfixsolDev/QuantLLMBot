@echo off
rem ===========================================================================
rem  Install-Autostart.bat - start QuantLLM (+ the trading model) at every
rem  Windows logon, with administrator rights.
rem
rem  Creates the Task Scheduler task "QuantLLM" for YOUR account:
rem    trigger   at logon, 60 s delay (Docker / the database come up first;
rem              the app also retries the database until it answers)
rem    runs      Start-QuantLLM.bat  (which starts Start-LLM.bat in its own window)
rem    rights    highest available (administrator)
rem    windows   visible on your desktop (MT5 needs your logged-in session)
rem
rem  Remove it again:   Install-Autostart.bat remove
rem  Note: MT5 must run at the same rights level as the app. If the app shows
rem  "MT5 not connected" after an autostart, start MetaTrader 5 "as administrator"
rem  too (or let the app start it: close MT5 before logging on).
rem  Check it:          schtasks /Query /TN QuantLLM /V /FO LIST
rem ===========================================================================
setlocal
cd /d "%~dp0"

rem ---- needs administrator rights: ask for them (UAC) and run again
net session >nul 2>&1
if errorlevel 1 (
  echo Asking for administrator rights...
  if "%~1"=="" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1' -Verb RunAs"
  )
  exit /b 0
)

if /i "%~1"=="remove" (
  schtasks /Delete /TN "QuantLLM" /F
  echo Autostart removed.
  pause
  exit /b 0
)

rem ---- the old pre-clean startup shortcut must not come back
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\QuantLLMBot Qwen Reviewer.lnk" (
  echo Note: an old "QuantLLMBot Qwen Reviewer" startup shortcut exists - it is the retired system; delete it.
)

schtasks /Create /F /TN "QuantLLM" /SC ONLOGON /RU "%USERDOMAIN%\%USERNAME%" /IT /RL HIGHEST /DELAY 0001:00 ^
  /TR "\"%~dp0Start-QuantLLM.bat\""
if errorlevel 1 (
  echo Could not create the task.
  pause
  exit /b 1
)
echo.
echo Autostart installed: QuantLLM and the trading model start 1 minute after you log on.
echo Test it now without logging off:   schtasks /Run /TN QuantLLM
pause
