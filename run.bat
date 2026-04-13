@echo off
:: run.bat
:: Run MicroAgent in development mode using the local .venv.
::
:: Usage:
::   run.bat              - start the interactive CLI
::   run.bat --help       - show main.py help (if any)
::
:: Prerequisites: run setup.bat at least once to create .venv.

setlocal

:: 1. Check that .venv exists
if not exist ".venv\Scripts\python.exe" (
    echo [run] ERROR: .venv not found. Run setup.bat first.
    exit /b 1
)

:: 2. Forward all arguments to main.py
".venv\Scripts\python.exe" main.py %*
exit /b %ERRORLEVEL%
