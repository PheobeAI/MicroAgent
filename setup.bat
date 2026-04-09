@echo off
:: setup.bat
:: Developer environment setup for MicroAgent.
:: Creates .venv, detects GPU (or use arg), installs correct llama-cpp-python variant.
::
:: Usage: setup.bat [cuda|vulkan|cpu]
::   (no args: auto-detects GPU via buildscripts\detect-gpu.bat)
::
:: After setup: activate venv with  .venv\Scripts\activate.bat
:: Or run directly:                 .venv\Scripts\python main.py

setlocal

set VARIANT=%1

echo [setup] MicroAgent Developer Setup
echo.

:: 1. Verify Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [setup] ERROR: Python not found. Install Python 3.10+ and add to PATH.
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [setup] Python %%v

:: 2. Create .venv if not present
if not exist ".venv" (
    echo [setup] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [setup] ERROR: Failed to create .venv
        exit /b 1
    )
)

:: 3. Activate .venv (pip commands below install into .venv)
call .venv\Scripts\activate.bat

:: 4. Auto-detect GPU variant if not specified
::    Two separate 'if' lines so %DETECTED_GPU% expands AFTER detect-gpu.bat sets it
if "%VARIANT%"=="" call buildscripts\detect-gpu.bat
if "%VARIANT%"=="" set VARIANT=%DETECTED_GPU%
echo [setup] GPU variant: %VARIANT%

:: 5. Install Vulkan SDK if needed (idempotent)
if /i "%VARIANT%"=="vulkan" (
    call buildscripts\install-vulkan-sdk.bat
    if errorlevel 1 (
        echo [setup] ERROR: Vulkan SDK installation failed
        exit /b 1
    )
)

:: 6. Install variant-specific llama-cpp-python + base requirements
call buildscripts\install-deps.bat %VARIANT%
if errorlevel 1 (
    echo [setup] ERROR: Dependency installation failed
    exit /b 1
)

:: 7. Install dev tools (pytest etc.)
pip install -r requirements-dev.txt
if errorlevel 1 (
    echo [setup] ERROR: Dev requirements install failed
    exit /b 1
)

:: 8. Done
echo.
echo [setup] Setup complete!
echo   GPU variant : %VARIANT%
echo   Virtual env : .venv\
echo   Activate    : .venv\Scripts\activate.bat
echo   Run app     : .venv\Scripts\python main.py
echo   Run tests   : .venv\Scripts\pytest tests/ -v
echo   Build       : build.bat %VARIANT% release
echo.

endlocal
exit /b 0
