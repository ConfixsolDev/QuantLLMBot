@echo off
rem ===========================================================================
rem  Start-LLM.bat - serve the trading model on http://127.0.0.1:8080
rem
rem  Bonsai 2 27B on the PrismML llama-server (Vulkan, AMD RX 6800).
rem  The trading system (backend\llm) talks to it through the OpenAI-
rem  compatible API; test with:  python -m llm ping   (from backend\)
rem
rem  Flags (why):
rem    -ngl 99        every layer on the GPU (16 GB VRAM: model 6 GB + cache)
rem    -fa on         flash attention
rem    -c 16384       context: a trading prompt is ~1,700 tokens; room for
rem                   reasoning "medium" if you ever turn it on
rem    -np 1          one slot = one conversation, no cache splitting
rem    --jinja        use the model's own chat template (reasoning_effort)
rem    (no --reasoning flag: the default "auto" lets each request choose;
rem     "--reasoning on" would override the client's "none")
rem  Local only (127.0.0.1): nothing outside this PC can reach it.
rem ===========================================================================
setlocal
title Bonsai 2 27B - trading model (llama-server :8080)
cd /d "%~dp0"
set "RT=%~dp0llm-runtime"
if "%LLM_MODEL%"=="" set "LLM_MODEL=%RT%\models\Ternary-Bonsai-2-27B-PTQ1_0.gguf"
if "%LLM_CTX%"=="" set "LLM_CTX=16384"

if not exist "%RT%\bin\llama-server.exe" (
  echo llama-server not found. Run Setup-LLM.bat first.
  pause
  exit /b 1
)
if not exist "%LLM_MODEL%" (
  echo Model file not found: %LLM_MODEL%
  echo Run Setup-LLM.bat first.
  pause
  exit /b 1
)
echo Starting Bonsai 2 27B on http://127.0.0.1:8080  (Ctrl+C to stop)
echo Check the log below: the model buffer must be on the Vulkan device ^(not "CPU model buffer" of several GB^).
"%RT%\bin\llama-server.exe" -m "%LLM_MODEL%" -ngl 99 -fa on -c %LLM_CTX% -np 1 --jinja --host 127.0.0.1 --port 8080
pause
