@echo off
chcp 65001 >nul
cd /d "%~dp0subtitle-remover"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "VENVPY=.venv\Scripts\python.exe"
set "TORCH_OK="

echo ============================================================
echo   AI (LaMa) setup for the Subtitle Eraser
echo   Folder: %~dp0
echo   Installs a GPU build of PyTorch + LaMa (a few GB). One time.
echo   Keep this window open until it says "AI installed".
echo ============================================================

if not exist "%VENVPY%" call :make_venv
if not exist "%VENVPY%" goto :no_python

echo.
echo [0/3] NVIDIA driver / GPU check (nvidia-smi)...
nvidia-smi
if errorlevel 1 echo     (nvidia-smi not found. If you have an NVIDIA GPU, update its driver at https://www.nvidia.com/drivers )

echo.
echo [1/3] Base packages + LaMa (this may pull a CPU torch; we replace it next)...
"%VENVPY%" -m pip install --upgrade pip
"%VENVPY%" -m pip install -r requirements.txt
"%VENVPY%" -m pip install simple-lama-inpainting

echo.
echo [2/3] Installing a GPU build of PyTorch (big download) and verifying CUDA...
call :try_torch cu124
if defined TORCH_OK goto :torch_done
call :try_torch cu126
if defined TORCH_OK goto :torch_done
call :try_torch cu121
if defined TORCH_OK goto :torch_done
call :try_torch cu118
if defined TORCH_OK goto :torch_done
echo.
echo     *** Could not get a working GPU build. Installing CPU build (VERY slow). ***
echo     *** Your driver seems OK, so this is usually a network issue -            ***
echo     *** just run this installer again. If it keeps happening, tell me.         ***
"%VENVPY%" -m pip uninstall -y torch torchvision >nul 2>nul
"%VENVPY%" -m pip install torch
:torch_done

echo.
echo [3/3] Result
echo ============================================================
"%VENVPY%" -c "import torch, simple_lama_inpainting; print('  Torch   :', torch.__version__); print('  GPU used:', torch.cuda.is_available()); print('  GPU name:', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU mode (SLOW)'))"
if errorlevel 1 goto :ai_failed
echo.
echo   AI installed. Open the Subtitle Eraser, upload a video, pick the "AI" engine.
echo     GPU used: True   -> fast (good).
echo     GPU used: False  -> CPU (very slow): run this installer again.
echo   (The very first erase downloads the model, about 200 MB.)
goto :done

:ai_failed
echo.
echo   *** AI setup FAILED. Send me the red/English error above. ***

:done
echo ============================================================
pause
exit /b 0

:try_torch
echo.
echo     - trying CUDA %1 ...
"%VENVPY%" -m pip uninstall -y torch torchvision >nul 2>nul
"%VENVPY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/%1
"%VENVPY%" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 1>nul 2>nul
if not errorlevel 1 set "TORCH_OK=1"
if defined TORCH_OK echo     -> CUDA %1 works (GPU detected).
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
