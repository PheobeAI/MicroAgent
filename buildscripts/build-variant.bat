@echo off
:: buildscripts/build-variant.bat
:: Compiles MicroAgent for one GPU variant using Nuitka.
::
:: Usage: build-variant.bat <cuda|vulkan|cpu> [release]
::   cuda|vulkan|cpu : GPU backend variant
::   release         : --onefile mode (distributable single exe)
::   (no mode arg)   : --standalone mode (faster, for local dev/testing)
::
:: Output:
::   dev:     dist\<variant>\microagent-<variant>.exe  (+ sibling DLLs)
::   release: dist\<variant>\microagent-<variant>.exe  (single file)

setlocal

set VARIANT=%1
set MODE=%2
if "%VARIANT%"=="" (
    echo [build-variant] ERROR: variant required ^(cuda^|vulkan^|cpu^)
    exit /b 1
)
if "%MODE%"=="" set MODE=dev

set BUILD_DIR=build\nuitka\%VARIANT%
set DIST_DIR=dist\%VARIANT%
set EXE_NAME=microagent-%VARIANT%.exe

echo [build-variant] Variant=%VARIANT%  Mode=%MODE%
echo [build-variant] Output: %DIST_DIR%\%EXE_NAME%

:: Clean dist dir, preserve models\ (may contain large .gguf files)
if exist "%DIST_DIR%" (
    for /d %%D in ("%DIST_DIR%\*") do if /i not "%%~nxD"=="models" rmdir /s /q "%%D"
    del /q "%DIST_DIR%\*" 2>nul
)
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

:: Install Nuitka (+ release-only compression extras)
if /i "%MODE%"=="release" (
    pip install nuitka zstandard ordered-set
) else (
    pip install nuitka
)
if errorlevel 1 (
    echo [build-variant] ERROR: Nuitka install failed
    exit /b 1
)

:: Common Nuitka flags shared by both modes
set NUITKA_FLAGS=^
  --include-package=smolagents ^
  --include-package-data=smolagents ^
  --include-package=llama_cpp ^
  --include-package=rich ^
  --include-package=psutil ^
  --include-package=pydantic ^
  --include-package=yaml ^
  --include-package=ddgs ^
  --include-package=tavily ^
  --output-filename=%EXE_NAME% ^
  --output-dir=%BUILD_DIR% ^
  --assume-yes-for-downloads ^
  --lto=no ^
  --nofollow-import-to=colorama.win32 ^
  --nofollow-import-to=starlette ^
  --nofollow-import-to=starlette_context

if /i "%MODE%"=="release" (
    python -m nuitka --onefile %NUITKA_FLAGS% main.py
) else (
    python -m nuitka --standalone %NUITKA_FLAGS% main.py
)
if errorlevel 1 (
    echo [build-variant] Build FAILED.
    exit /b 1
)

:: Stage distribution artifacts
if /i "%MODE%"=="release" (
    copy "%BUILD_DIR%\%EXE_NAME%" "%DIST_DIR%\%EXE_NAME%"
    if errorlevel 1 (
        echo [build-variant] ERROR: Failed to copy exe to dist
        exit /b 1
    )
) else (
    xcopy /e /i /y "%BUILD_DIR%\main.dist" "%DIST_DIR%\"
)
copy config.yaml "%DIST_DIR%\config.yaml" 2>nul
copy README.txt "%DIST_DIR%\README.txt" 2>nul
if not exist "%DIST_DIR%\models" mkdir "%DIST_DIR%\models"

echo.
echo [build-variant] Done: %DIST_DIR%\%EXE_NAME%
endlocal
exit /b 0
