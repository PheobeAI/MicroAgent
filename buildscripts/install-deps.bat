@echo off
:: buildscripts/install-deps.bat
:: Installs llama-cpp-python for the specified GPU variant, then requirements-base.txt
::
:: Usage: install-deps.bat <cuda|vulkan|cpu>
::
:: CUDA: Uses official pre-built wheel from the llama-cpp-python CUDA index.
::   Default CUDA wheel: cu124 (compatible with CUDA 12.x and 13.x via NVIDIA backward compat)
::   Override: set LLAMA_CUDA_VERSION=cu125 before calling
::   Two-step install: CUDA wheel from CUDA index first (--no-deps, so PyPI cannot override),
::   then deps from PyPI (pip sees llama-cpp-python satisfied, only fetches missing deps).
::
:: Vulkan: Compiles llama-cpp-python from source. Prerequisites:
::   - VULKAN_SDK env var set (run install-vulkan-sdk.bat first)
::   - VS 2022 Build Tools with C++ workload
::   - CMake in PATH
::
:: CPU: Standard PyPI wheel, no GPU needed.

setlocal

set VARIANT=%1
if "%VARIANT%"=="" (
    echo [install-deps] ERROR: variant required ^(cuda^|vulkan^|cpu^)
    exit /b 1
)

echo [install-deps] Installing llama-cpp-python ^(%VARIANT%^)...

:: Set CUDA default BEFORE the if block — %VAR% expands at block-parse time in cmd.exe
if "%LLAMA_CUDA_VERSION%"=="" set LLAMA_CUDA_VERSION=cu124

if /i "%VARIANT%"=="cuda"   goto :do_cuda
if /i "%VARIANT%"=="vulkan" goto :do_vulkan
if /i "%VARIANT%"=="cpu"    goto :do_cpu

echo [install-deps] ERROR: Unknown variant: %VARIANT%
exit /b 1

:do_cuda
echo [install-deps] CUDA wheel: %LLAMA_CUDA_VERSION%
:: Step 1: Install llama-cpp-python from the CUDA index ONLY.
::         --index-url (not --extra-index-url) prevents pip from seeing the higher
::         CPU-only version on PyPI and picking it over the CUDA wheel.
::         --no-deps so pip doesn't fail looking for numpy etc. on the CUDA-only index.
pip install "llama-cpp-python>=0.2.90" ^
    --index-url "https://abetlen.github.io/llama-cpp-python/whl/%LLAMA_CUDA_VERSION%" ^
    --no-deps
if errorlevel 1 (
    echo [install-deps] ERROR: CUDA wheel install failed
    exit /b 1
)
:: Step 2: Install transitive deps from PyPI.
::         pip sees llama-cpp-python already satisfied, only fetches missing deps.
pip install "llama-cpp-python>=0.2.90"
if errorlevel 1 (
    echo [install-deps] ERROR: CUDA deps install failed
    exit /b 1
)
goto :install_base

:do_vulkan
if not defined VULKAN_SDK (
    echo [install-deps] ERROR: VULKAN_SDK not set. Run buildscripts\install-vulkan-sdk.bat first.
    exit /b 1
)
echo [install-deps] Building Vulkan wheel ^(VULKAN_SDK=%VULKAN_SDK%^)...
set CMAKE_ARGS=-DGGML_VULKAN=on
pip install "llama-cpp-python>=0.2.90" --no-binary :all:
if errorlevel 1 (
    echo [install-deps] ERROR: Vulkan source build failed
    exit /b 1
)
goto :install_base

:do_cpu
pip install "llama-cpp-python>=0.2.90"
if errorlevel 1 (
    echo [install-deps] ERROR: CPU wheel install failed
    exit /b 1
)
goto :install_base

:install_base
echo [install-deps] Installing requirements-base.txt...
pip install -r requirements-base.txt
if errorlevel 1 (
    echo [install-deps] ERROR: requirements-base.txt install failed
    exit /b 1
)
echo [install-deps] Done.
endlocal
exit /b 0
