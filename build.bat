@echo off
setlocal
echo [MicroAgent] Starting build...

:: ---------- mode ----------
:: Usage: build.bat           -> dev mode  (directory, fast)
::        build.bat release   -> release mode (onefile, distributable)
set MODE=dev
if /i "%1"=="release" set MODE=release
echo [MicroAgent] Mode: %MODE%

:: ---------- directories ----------
set BUILD_DIR=build\nuitka
set DIST_DIR=dist

:: Clean distribution directory, but preserve models\ (may contain large .gguf files)
if exist "%DIST_DIR%" (
  for /d %%D in ("%DIST_DIR%\*") do if /i not "%%~nxD"=="models" rmdir /s /q "%%D"
  del /q "%DIST_DIR%\*" 2>nul
)
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

:: ---------- dependencies ----------
if "%MODE%"=="release" (
  pip install nuitka zstandard ordered-set
) else (
  pip install nuitka
)

:: ---------- compile ----------
if "%MODE%"=="release" (
  python -m nuitka ^
    --onefile ^
    --include-package=smolagents ^
    --include-package-data=smolagents ^
    --include-package=llama_cpp ^
    --include-package=rich ^
    --include-package=psutil ^
    --include-package=pydantic ^
    --include-package=yaml ^
    --include-package=ddgs ^
    --include-package=tavily ^
    --output-filename=microagent.exe ^
    --output-dir="%BUILD_DIR%" ^
    --assume-yes-for-downloads ^
    --lto=no ^
    --nofollow-import-to=colorama.win32 ^
    --nofollow-import-to=starlette ^
    --nofollow-import-to=starlette_context ^
    main.py
) else (
  python -m nuitka ^
    --standalone ^
    --include-package=smolagents ^
    --include-package-data=smolagents ^
    --include-package=llama_cpp ^
    --include-package=rich ^
    --include-package=psutil ^
    --include-package=pydantic ^
    --include-package=yaml ^
    --include-package=ddgs ^
    --include-package=tavily ^
    --output-filename=microagent.exe ^
    --output-dir="%BUILD_DIR%" ^
    --assume-yes-for-downloads ^
    --lto=no ^
    --nofollow-import-to=colorama.win32 ^
    --nofollow-import-to=starlette ^
    --nofollow-import-to=starlette_context ^
    main.py
)

if errorlevel 1 (
  echo.
  echo [MicroAgent] Build FAILED.
  exit /b 1
)

:: ---------- stage distribution ----------
if "%MODE%"=="release" (
  copy "%BUILD_DIR%\microagent.exe" "%DIST_DIR%\microagent.exe"
) else (
  xcopy /e /i /y "%BUILD_DIR%\main.dist" "%DIST_DIR%"
)

copy config.yaml "%DIST_DIR%\config.yaml"
copy README.txt "%DIST_DIR%\README.txt"

:: models\ preserved across rebuilds — user places .gguf files here
if not exist "%DIST_DIR%\models" mkdir "%DIST_DIR%\models"

:: ---------- done ----------
echo.
echo [MicroAgent] Distribution ready in %DIST_DIR%\
echo.
if "%MODE%"=="release" (
  echo   %DIST_DIR%\microagent.exe    (single file)
) else (
  echo   %DIST_DIR%\microagent.exe    (+ DLLs, run from this directory)
)
echo   %DIST_DIR%\config.yaml
echo   %DIST_DIR%\models\          (place .gguf model files here)
echo   %DIST_DIR%\README.txt
endlocal
