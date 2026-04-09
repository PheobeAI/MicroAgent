@echo off
:: build.bat
:: Local build entry point — thin dispatcher to buildscripts\build-variant.bat
::
:: Usage: build.bat [cuda|vulkan|cpu|all] [release]
::   cuda|vulkan|cpu  : build single variant (default: cuda)
::   all              : build all three variants sequentially
::   release          : onefile distributable (default: standalone dev mode)
::
:: Examples:
::   build.bat                  -> cuda, dev (fast)
::   build.bat vulkan           -> vulkan, dev
::   build.bat cuda release     -> cuda, onefile release
::   build.bat all release      -> all three release variants

setlocal

set VARIANT=%1
set MODE=%2
if "%VARIANT%"=="" set VARIANT=cuda
if "%MODE%"=="" set MODE=dev

:: Activate .venv if present and not already in a virtual env
if not defined VIRTUAL_ENV (
    if exist ".venv\Scripts\activate.bat" (
        call .venv\Scripts\activate.bat
    )
)

if /i "%VARIANT%"=="all" (
    echo [build] Building all variants ^(mode: %MODE%^)...
    call buildscripts\build-variant.bat cuda %MODE%
    if errorlevel 1 exit /b 1
    call buildscripts\build-variant.bat vulkan %MODE%
    if errorlevel 1 exit /b 1
    call buildscripts\build-variant.bat cpu %MODE%
    if errorlevel 1 exit /b 1
    echo.
    echo [build] All variants complete:
    echo   dist\cuda\microagent-cuda.exe
    echo   dist\vulkan\microagent-vulkan.exe
    echo   dist\cpu\microagent-cpu.exe
) else (
    call buildscripts\build-variant.bat %VARIANT% %MODE%
    if errorlevel 1 exit /b 1
)

endlocal
exit /b 0
