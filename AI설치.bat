@echo off
chcp 65001 >nul
cd /d "%~dp0subtitle-remover"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "VENVPY=.venv\Scripts\python.exe"

echo ============================================================
echo   AI (LaMa) setup for the Subtitle Eraser
echo   Folder: %~dp0
echo   Downloads PyTorch + LaMa (about 3 GB). One time only.
echo   Keep this window open until it says "AI ready".
echo ============================================================

if not exist "%VENVPY%" call :make_venv
if not exist "%VENVPY%" goto :no_python

echo.
echo [1/3] Base packages...
"%VENVPY%" -m pip install --upgrade pip
"%VENVPY%" -m pip install -r requirements.txt

echo.
echo [2/3] PyTorch (trying GPU / CUDA 12.1)...
"%VENVPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu121
"%VENVPY%" -c "import torch" 1>nul 2>nul
if not errorlevel 1 goto :torch_ok
echo     cu121 did not work, trying CUDA 11.8...
"%VENVPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu118
"%VENVPY%" -c "import torch" 1>nul 2>nul
if not errorlevel 1 goto :torch_ok
echo     GPU build failed. Installing CPU build (works, but slow)...
"%VENVPY%" -m pip install torch
:torch_ok

echo.
echo [3/3] LaMa inpainting...
"%VENVPY%" -m pip install simple-lama-inpainting

echo.
echo ============================================================
"%VENVPY%" -c "import torch, simple_lama_inpainting; print('  Torch   :', torch.__version__); print('  GPU used:', torch.cuda.is_available()); print('  GPU name:', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU mode (slow)'))"
if errorlevel 1 goto :ai_failed
echo.
echo   AI ready!  Open the Subtitle Eraser, upload a video, and pick
echo   the "AI" engine in the right panel.
echo   (The very first erase downloads the model, about 200 MB.)
goto :done

:ai_failed
echo.
echo   *** AI setup FAILED. Send me the red/English error above. ***

:done
echo ============================================================
pause
exit /b 0

:make_venv
echo [Setup] Creating Python environment...
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
exit /b 0

:no_python
echo.
echo *** Python not found. Install Python 3.12 from https://www.python.org/downloads/
echo     and check "Add Python to PATH". Then run this again. ***
pause
exit /b 1
