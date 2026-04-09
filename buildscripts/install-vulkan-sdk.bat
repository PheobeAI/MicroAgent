@echo off
:: buildscripts/install-vulkan-sdk.bat
:: Installs Vulkan SDK via winget if not already present.
:: Idempotent: skips if VULKAN_SDK env var already points to a valid SDK.
:: In GitHub Actions: writes VULKAN_SDK path to GITHUB_ENV for subsequent steps.
:: Usage: call buildscripts\install-vulkan-sdk.bat

setlocal EnableDelayedExpansion

:: Check if already installed (VULKAN_SDK env var + lib file present)
if defined VULKAN_SDK (
    if exist "%VULKAN_SDK%\Lib\vulkan-1.lib" (
        echo [install-vulkan-sdk] Already installed: %VULKAN_SDK%
        endlocal & set VULKAN_SDK=%VULKAN_SDK%
        exit /b 0
    )
)

echo [install-vulkan-sdk] Installing Vulkan SDK via winget...
winget install KhronosGroup.VulkanSDK --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo [install-vulkan-sdk] ERROR: winget install failed
    exit /b 1
)

:: Discover installed SDK path (newest version under C:\VulkanSDK\)
set SDK_PATH=
for /d %%D in ("C:\VulkanSDK\*") do set SDK_PATH=%%D

if "!SDK_PATH!"=="" (
    echo [install-vulkan-sdk] ERROR: Cannot find SDK under C:\VulkanSDK\
    exit /b 1
)

echo [install-vulkan-sdk] Installed: !SDK_PATH!

:: In GitHub Actions: export to GITHUB_ENV so subsequent steps see VULKAN_SDK
if defined GITHUB_ENV (
    echo VULKAN_SDK=!SDK_PATH!>> "%GITHUB_ENV%"
    echo [install-vulkan-sdk] VULKAN_SDK written to GITHUB_ENV
)

:: Propagate VULKAN_SDK out of setlocal scope to caller
endlocal & set VULKAN_SDK=%SDK_PATH%
exit /b 0
