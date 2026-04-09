@echo off
:: buildscripts/install-deps.bat
:: Installs llama-cpp-python for the specified GPU variant, then requirements-base.txt
::
:: Usage: install-deps.bat <cuda|vulkan|cpu>
::
:: CUDA: Compiles llama-cpp-python from source with CUDA support. Prerequisites:
::   - CUDA Toolkit (CUDA_PATH env var set, or nvcc in PATH)
::   - VS 2022 Build Tools with C++ workload (auto-detected)
::   - CMake and Ninja in PATH (Ninja installed via pip if absent)
::   Note: source build required because prebuilt CUDA wheels are outdated and
::   do not support newer model architectures (e.g. gemma4).
::
:: Vulkan: Compiles llama-cpp-python from source. Prerequisites:
::   - VULKAN_SDK env var set (run install-vulkan-sdk.bat first)
::   - VS 2022 Build Tools with C++ workload
::   - CMake in PATH
::
:: CPU: Standard PyPI wheel, no GPU needed.

setlocal EnableDelayedExpansion

set VARIANT=%1
if "%VARIANT%"=="" (
    echo [install-deps] ERROR: variant required ^(cuda^|vulkan^|cpu^)
    exit /b 1
)

echo [install-deps] Installing llama-cpp-python ^(%VARIANT%^)...

if /i "%VARIANT%"=="cuda"   goto :do_cuda
if /i "%VARIANT%"=="vulkan" goto :do_vulkan
if /i "%VARIANT%"=="cpu"    goto :do_cpu

echo [install-deps] ERROR: Unknown variant: %VARIANT%
exit /b 1

:do_cuda
:: Verify CUDA Toolkit
if not defined CUDA_PATH (
    where nvcc >nul 2>&1
    if errorlevel 1 (
        echo [install-deps] ERROR: CUDA_PATH not set and nvcc not in PATH.
        echo [install-deps]        Install CUDA Toolkit and ensure nvcc is in PATH.
        exit /b 1
    )
)
echo [install-deps] Building CUDA wheel from source ^(CUDA_PATH=%CUDA_PATH%^)...

:: Ensure Ninja is available (needed for CUDA builds without VS CUDA toolset)
where ninja >nul 2>&1
if errorlevel 1 (
    echo [install-deps] Ninja not found, installing via pip...
    pip install ninja
    if errorlevel 1 (
        echo [install-deps] ERROR: Failed to install ninja
        exit /b 1
    )
)

:: Auto-detect VS installation and set up compiler environment for Ninja
call :setup_vs_env

:: Download the source distribution (avoids the prebuilt pure-Python wheel
:: which does not include CUDA support)
set LLAMA_SDIST_DIR=%TEMP%\microagent_llama_sdist
if not exist "%LLAMA_SDIST_DIR%" mkdir "%LLAMA_SDIST_DIR%"
echo [install-deps] Downloading llama-cpp-python source...
pip download "llama-cpp-python>=0.2.90" --no-binary :all: --no-deps -d "%LLAMA_SDIST_DIR%"
if errorlevel 1 (
    echo [install-deps] ERROR: Failed to download llama-cpp-python source
    exit /b 1
)

:: Install from source with CUDA flags and Ninja generator
set CMAKE_ARGS=-DGGML_CUDA=on -G Ninja
set _SDIST_FOUND=0
for %%F in ("%LLAMA_SDIST_DIR%\llama_cpp_python*.tar.gz") do (
    set _SDIST_FOUND=1
    echo [install-deps] Building from %%~nxF ...
    pip install "%%F"
    if errorlevel 1 (
        echo [install-deps] ERROR: CUDA source build failed
        exit /b 1
    )
)
if "!_SDIST_FOUND!"=="0" (
    echo [install-deps] ERROR: No llama-cpp-python sdist found in %LLAMA_SDIST_DIR%
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
pip install "llama-cpp-python>=0.2.90" --no-binary llama-cpp-python
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

:: -----------------------------------------------------------------------
:setup_vs_env
:: Auto-detect VS 2022 installation and initialize MSVC compiler environment.
:: Needed for Ninja-based builds (CUDA) to find cl.exe, link.exe, etc.
:: Silently succeeds if the environment is already initialized.
set "_VCA="
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    set "_VCA=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
)
if not defined _VCA if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" (
    set "_VCA=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat"
)
if not defined _VCA if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat" (
    set "_VCA=C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat"
)
if not defined _VCA if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" (
    set "_VCA=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
)
if not defined _VCA (
    echo [install-deps] VS 2022 not found at known paths, skipping vcvarsall.
    exit /b 1
)
echo [install-deps] Initializing VS environment: !_VCA!
call "!_VCA!" x64
exit /b 0
