@echo off
rem ===========================================================================
rem  Setup-LLM.bat - one-time download of the trading model and its runtime.
rem
rem  Model   : Bonsai 2 27B  (prism-ml/Ternary-Bonsai-2-27B-gguf)  ~6 GB
rem  Runtime : PrismML fork of llama.cpp, Windows x64 VULKAN build
rem
rem  Why Vulkan on this PC (AMD Radeon RX 6800, RDNA2 / gfx1030):
rem    - the model's PTQ1_0 / PQ2_0 files run ONLY on the PrismML fork
rem      (Ollama, LM Studio and stock llama.cpp cannot load them);
rem    - the fork's HIP/ROCm build aborts on RDNA2 cards (known issue),
rem      the Vulkan build is the supported path for AMD on Windows.
rem  Model file: PTQ1_0 (5.95 GB) - runs on the GPU in the Vulkan release.
rem  (PQ2_0, 7.2 GB, ran on the CPU under Vulkan in older releases.)
rem
rem  Everything goes to .\llm-runtime\ (not in git). Re-running is safe.
rem ===========================================================================
setlocal
cd /d "%~dp0"
set "RT=%~dp0llm-runtime"
set "REL=prism-b10772-e8fd209"
set "ZIP=llama-%REL%-bin-win-vulkan-x64.zip"
set "BIN_URL=https://github.com/PrismML-Eng/llama.cpp/releases/download/%REL%/%ZIP%"
set "MODEL=Ternary-Bonsai-2-27B-PTQ1_0.gguf"
set "MODEL_URL=https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf/resolve/main/%MODEL%"

if not exist "%RT%\bin" mkdir "%RT%\bin"
if not exist "%RT%\models" mkdir "%RT%\models"

if exist "%RT%\bin\llama-server.exe" (
  echo [ok] llama-server already installed
) else (
  echo Downloading the PrismML llama.cpp Vulkan build %REL% ...
  curl.exe -L --fail -o "%RT%\%ZIP%" "%BIN_URL%" || goto :fail
  powershell -NoProfile -Command "Expand-Archive -Force '%RT%\%ZIP%' '%RT%\bin'" || goto :fail
  for /r "%RT%\bin" %%f in (llama-server.exe) do if exist "%%f" if not "%%~dpf"=="%RT%\bin\" xcopy /y /q "%%~dpf*" "%RT%\bin\" >nul
  del "%RT%\%ZIP%"
)

if exist "%RT%\models\%MODEL%" (
  echo [ok] model already downloaded
) else (
  rem download to .part and rename only when curl finishes OK, so an
  rem interrupted download is resumed next run instead of being treated as done
  echo Downloading %MODEL% ^(5.95 GB^) ...
  curl.exe -L --fail --retry 20 --retry-all-errors --retry-delay 5 -C - -o "%RT%\models\%MODEL%.part" "%MODEL_URL%" || goto :fail
  move /y "%RT%\models\%MODEL%.part" "%RT%\models\%MODEL%" >nul || goto :fail
)

"%RT%\bin\llama-server.exe" --version
echo.
echo Done. Start the model with Start-LLM.bat
pause
exit /b 0

:fail
echo Download failed. Check the internet connection and run Setup-LLM.bat again (downloads resume).
pause
exit /b 1
