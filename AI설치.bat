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
echo   Keep this window open until it says "AI installed".
echo ============================================================

if not exist "%VENVPY%" call :make_venv
if not exist "%VENVPY%" goto :no_python

echo.
echo [0/4] NVIDIA driver / GPU check (nvidia-smi)...
nvidia-smi
if errorlevel 1 echo     (nvidia-smi not found. If you have an NVIDIA GPU, update its driver from nvidia.com/drivers.)

echo.
echo [1/4] Base packages...
"%VENVPY%" -m pip install --upgrade pip
"%VENVPY%" -m pip install -r requirements.txt

echo.
echo [2/4] PyTorch with GPU support (this is the big download)...
echo     - trying CUDA 12.1 ...
"%VENVPY%" -m pip uninstall -y torch >nul 2>nul
"%VENVPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu121
"%VENVPY%" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 1>nul 2>nul
if not errorlevel 1 goto :torch_ok
echo     - CUDA 12.1 not usable here, trying CUDA 11.8 ...
"%VENVPY%" -m pip uninstall -y torch >nul 2>nul
"%VENVPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu118
"%VENVPY%" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 1>nul 2>nul
if not errorlevel 1 goto :torch_ok
echo.
echo     *** GPU was NOT detected. Installing CPU build (works, but VERY slow). ***
echo     *** To use the GPU: update your NVIDIA driver (GeForce Experience or    ***
echo     *** https://www.nvidia.com/drivers ), then run this installer again.    ***
"%VENVPY%" -m pip uninstall -y torch >nul 2>nul
"%VENVPY%" -m pip install torch
:torch_ok

echo.
echo [3/4] LaMa inpainting...
"%VENVPY%" -m pip install simple-lama-inpainting

echo.
echo [4/4] Result
echo ============================================================
"%VENVPY%" -c "import torch, simple_lama_inpainting; print('  Torch   :', torch.__version__); print('  GPU used:', torch.cuda.is_available()); print('  GPU name:', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU mode (SLOW)'))"
if errorlevel 1 goto :ai_failed
echo.
echo   AI installed. Open the Subtitle Eraser, upload a video, pick the "AI" engine.
echo     GPU used: True   -> fast (good).
echo     GPU used: False  -> CPU (very slow): update the NVIDIA driver and run this again.
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
