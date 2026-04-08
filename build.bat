@echo off
echo [MicroAgent] Starting Nuitka build...

pip install nuitka zstandard ordered-set

python -m nuitka ^
  --onefile ^
  --include-package=smolagents ^
  --include-package=llama_cpp ^
  --include-package=rich ^
  --include-package=psutil ^
  --include-package=pydantic ^
  --include-package=yaml ^
  --include-package=duckduckgo_search ^
  --include-package=tavily ^
  --include-data-files=config.yaml=config.yaml ^
  --enable-plugin=anti-bloat ^
  --output-filename=microagent.exe ^
  --output-dir=dist ^
  main.py

echo.
echo [MicroAgent] Build complete: dist\microagent.exe
echo Copy dist\microagent.exe + config.yaml + models\ to distribute.
pause
