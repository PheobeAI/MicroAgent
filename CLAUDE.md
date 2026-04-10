# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MicroAgent is a lightweight local AI agent framework targeting Windows systems with limited GPU resources (AMD Ryzen iGPU). It runs GGUF models via `llama-cpp-python`, orchestrates tool use through `smolagents`, and bundles to a standalone `.exe` via Nuitka. Three distribution variants exist: **cuda**, **vulkan** (AMD), and **cpu**.

## Commands

### Development Setup
```bash
# Auto-detect GPU, create .venv, install deps
setup.bat

# Or specify variant explicitly
setup.bat cuda | vulkan | cpu
```

### Run
```bash
.venv\Scripts\activate.bat
python main.py
```

### Build
```bash
# Dev build (directory, fast startup for local testing)
build.bat cuda | vulkan | cpu

# Release build (onefile distributable)
build.bat cuda release
build.bat all release   # all three variants sequentially
```
Output: `dist\<variant>\microagent-<variant>.exe`

### Tests
```bash
.venv\Scripts\activate.bat
pytest tests/ -v

# Single test file
pytest tests/test_config.py -v
```

### Release
```bash
git tag v0.x.y
git push origin v0.x.y  # triggers GitHub Actions: parallel 3-variant build + GitHub Release
```

## Architecture

### Data Flow
```
User Input (CLI) → main.py → AgentRunner → LlamaCppBackend (Gemma-4) → Tool Calls → CLI output
```

### Key Modules

**`main.py`** — Entry point. Loads `config.yaml` (resolved relative to the exe), wires up model → registry → agent → CLI.

**`core/config.py`** — Pydantic `AppConfig` hierarchy (`ModelConfig`, `AgentConfig`, `ToolsConfig`, `RuntimeConfig`). All relative model paths are resolved against the config file's directory at load time, not at runtime.

**`core/model.py`** — `LlamaCppBackend` wraps llama-cpp-python. **Critical detail**: `tools_to_call_from` is intentionally NOT passed to the llama-cpp call — doing so strips special tokens and breaks Gemma's native tool-call format. The inner `_LlamaCppSmolagentsModel` uses regex to parse Gemma's `<|tool_call>call:NAME{...}<|tool_call|>` format into smolagents `ChatMessage` objects.

**`core/agent.py`** — Abstract `AgentRunner` with two implementations:
- `ToolCallingAgentRunner` (recommended): always injects `ThinkTool`, mandates tool calls on every response
- `CodeAgentRunner`: alternative for stronger models (Python code execution)

**`tools/`** — All tools extend `MicroTool` (subclass of smolagents `Tool`). Define `name`, `description`, `inputs`, `output_type`, and `forward()`. Destructive tools (`WriteFileTool`, `DeleteFileTool`, etc.) check an `allowed_dirs` whitelist before operating and require `allow_destructive: true` in config.

**`cli/app.py`** — Interactive Rich loop. Slash commands: `/help`, `/tools`, `/clear`, `/config`.

**`ui/console.py`** — Shared Rich `Console` instance pinned to the original stdout. Must be used by all output (including ThinkTool and spinners) to survive llama.cpp's stderr redirection.

### Adding a Tool
1. Create a class in `tools/` extending `MicroTool`
2. Define `name`, `description`, `inputs` (dict), `output_type`, and `forward(**kwargs)`
3. Register it in `tools/registry.py`
4. Add a feature flag under `tools:` in `config.yaml`

### CUDA Build Notes
llama-cpp-python is compiled **from source** for CUDA because pre-built Windows CUDA wheels on the abetlen index only go up to v0.3.4 and don't support the gemma4 architecture. `install-deps.bat cuda` downloads the sdist via `pip download --no-binary :all: --no-deps`, then builds with `CMAKE_ARGS=-DGGML_CUDA=on -G Ninja`. Requires: CUDA Toolkit, VS 2022 Build Tools, Ninja (auto-installed via pip if absent).

**CI note**: The GitHub Actions CUDA job uses `Jimver/cuda-toolkit` with `method: 'local'` (full toolkit download, no `sub-packages` filter). The network installer's sub-package naming is unreliable on Windows Server 2025 — specifying individual packages causes exit code `0xE0E00019`.
