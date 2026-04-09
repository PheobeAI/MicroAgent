@echo off
:: buildscripts/detect-gpu.bat
:: Detects current GPU type and sets DETECTED_GPU=cuda|vulkan|cpu
:: Usage: call buildscripts\detect-gpu.bat
::        then read %DETECTED_GPU%
:: Note: No setlocal — DETECTED_GPU propagates to the caller's environment

nvidia-smi >nul 2>&1
if not errorlevel 1 (
    set DETECTED_GPU=cuda
    echo [detect-gpu] NVIDIA GPU detected ^(cuda^)
    exit /b 0
)

wmic path win32_VideoController get Caption 2>nul | findstr /i "AMD Radeon" >nul
if not errorlevel 1 (
    set DETECTED_GPU=vulkan
    echo [detect-gpu] AMD Radeon GPU detected ^(vulkan^)
    exit /b 0
)

set DETECTED_GPU=cpu
echo [detect-gpu] No dedicated GPU detected ^(cpu^)
exit /b 0
