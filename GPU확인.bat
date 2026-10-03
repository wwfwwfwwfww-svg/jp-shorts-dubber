@echo off
chcp 65001 >nul
cd /d "%~dp0subtitle-remover"
set "VENVPY=.venv\Scripts\python.exe"

echo ============================================================
echo   GPU / AI diagnostic (no install, just a check)
echo   Folder: %~dp0
echo ============================================================

echo.
echo [1] NVIDIA driver / GPU (nvidia-smi):
nvidia-smi
if errorlevel 1 echo     nvidia-smi NOT found -> no usable NVIDIA driver. Update it at https://www.nvidia.com/drivers

echo.
echo [2] PyTorch in the app environment:
if not exist "%VENVPY%" goto :novenv
"%VENVPY%" -c "import torch; print('  Torch   :', torch.__version__); print('  GPU used:', torch.cuda.is_available()); print('  GPU name:', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'))" 2>nul
if errorlevel 1 echo     PyTorch not installed yet. Run AI setup first.
goto :done

:novenv
echo     Environment not created yet. Run the Subtitle Eraser (or AI setup) once first.

:done
echo ============================================================
echo   If GPU used: False but nvidia-smi shows your GPU  -> wrong torch, re-run AI setup.
echo   If nvidia-smi is missing/old                       -> update NVIDIA driver, then AI setup.
echo ============================================================
pause
