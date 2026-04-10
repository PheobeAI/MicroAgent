# Step 0: Config Lookup & Directory Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `core/paths.py` as the single source of truth for all runtime paths, and update `main.py`, `core/config.py`, and `ui/logger.py` to use it — replacing ad-hoc path logic and fixing the inconsistent log directory.

**Architecture:** `core/paths.py` owns `USER_DIR = Path.home() / ".pheobe" / "MicroAgent"` and exposes `find_config()` (3-step lookup with auto-bootstrap), `resolve_relative()` (config-relative path resolution), and `log_dir()`. `main.py` calls `find_config()` then `resolve_relative()` for the model path. `ui/logger.py` replaces its hardcoded `_log_dir()` with an import. `core/config.py` removes the model path resolution it currently owns.

**Tech Stack:** Python stdlib only — `pathlib`, `shutil`, `sys`

---

### Task 1: 创建 `core/paths.py`（TDD — resolve_relative）

**Files:**
- Create: `core/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 1: 写失败测试 — `resolve_relative`**

新建 `tests/test_paths.py`，内容：

```python
# tests/test_paths.py
from pathlib import Path


def test_resolve_relative_absolute_passthrough(tmp_path):
    """绝对路径直通，不做任何修改"""
    from core.paths import resolve_relative
    abs_path = str(tmp_path / "model.gguf")
    result = resolve_relative(tmp_path, abs_path)
    assert result == Path(abs_path)


def test_resolve_relative_resolves_against_config_dir(tmp_path):
    """相对路径相对于 config_dir 解析"""
    from core.paths import resolve_relative
    result = resolve_relative(tmp_path, r"models\foo.gguf")
    assert result == (tmp_path / "models" / "foo.gguf").resolve()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_paths.py -v
```

预期：`ImportError: No module named 'core.paths'`

- [ ] **Step 3: 创建 `core/paths.py`**

```python
# core/paths.py
import shutil
import sys
from pathlib import Path

USER_DIR: Path = Path.home() / ".pheobe" / "MicroAgent"
_SUBDIRS = ("models", "memory", "logs", "skills")

_DEFAULT_CONFIG = """\
# MicroAgent 配置文件
# 所有路径均相对于本文件所在目录

model:
  path: models\\gemma-4-e2b-instruct.gguf
  n_gpu_layers: -1
  n_threads: 6
  n_ctx: 131072
  max_tokens: 2048

agent:
  mode: tool_calling
  verbose: false
  show_thinking: true

tools:
  web_search:
    enabled: true
    tavily_api_key: ""
  file_manager:
    enabled: true
    allow_destructive: false
    allowed_dirs: []
  system_info:
    enabled: true

runtime:
  language: zh
  log_level: info
"""


def get_exe_dir() -> Path:
    """exe 所在目录；开发时为 main.py 所在目录。"""
    return Path(sys.argv[0]).resolve().parent


def resolve_relative(config_dir: Path, value: str) -> Path:
    """相对路径相对于 config_dir 解析；绝对路径直通。"""
    p = Path(value)
    if p.is_absolute():
        return p
    return (config_dir / p).resolve()


def bootstrap_user_dir(template: Path | None = None) -> Path:
    """创建 USER_DIR 目录树，写入/复制 config.yaml。返回 USER_DIR。"""
    try:
        for sub in _SUBDIRS:
            (USER_DIR / sub).mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"[ERROR] 无法创建用户目录 {USER_DIR}: {e}")
        sys.exit(1)

    config_dest = USER_DIR / "config.yaml"
    if not config_dest.exists():
        if template is not None and template.exists():
            try:
                shutil.copy(template, config_dest)
            except Exception:
                config_dest.write_text(_DEFAULT_CONFIG, encoding="utf-8")
        else:
            config_dest.write_text(_DEFAULT_CONFIG, encoding="utf-8")

    return USER_DIR


def find_config() -> Path:
    """三步查找 config.yaml；不存在时自动 bootstrap，返回 config 路径。"""
    user_config = USER_DIR / "config.yaml"
    if user_config.exists():
        return user_config

    exe_config = get_exe_dir() / "config.yaml"
    if exe_config.exists():
        return exe_config

    bootstrap_user_dir(template=exe_config)
    return USER_DIR / "config.yaml"


def log_dir() -> Path:
    """返回日志目录，不存在则创建。"""
    d = USER_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_paths.py -v
```

预期：2 个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add core/paths.py tests/test_paths.py
git commit -m "feat(paths): add core/paths.py with resolve_relative (TDD)"
```

---

### Task 2: TDD — `bootstrap_user_dir`

**Files:**
- Modify: `tests/test_paths.py`

- [ ] **Step 1: 在 `tests/test_paths.py` 末尾追加 bootstrap 测试**

```python
def test_bootstrap_creates_subdirs(tmp_path, monkeypatch):
    """bootstrap_user_dir 创建四个子目录"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    from core.paths import bootstrap_user_dir
    result = bootstrap_user_dir()

    assert result == user_dir
    for sub in ("models", "memory", "logs", "skills"):
        assert (user_dir / sub).is_dir(), f"缺少子目录: {sub}"


def test_bootstrap_copies_template(tmp_path, monkeypatch):
    """提供 template 时复制其内容"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    template = tmp_path / "config.yaml"
    template.write_text("model:\n  path: test.gguf\n", encoding="utf-8")

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=template)

    dest = user_dir / "config.yaml"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "model:\n  path: test.gguf\n"


def test_bootstrap_writes_default_when_no_template(tmp_path, monkeypatch):
    """无 template 时写入内置默认配置，文件可被 yaml.safe_load 解析"""
    import yaml
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=None)

    dest = user_dir / "config.yaml"
    assert dest.exists()
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "model" in data
    assert "agent" in data
```

- [ ] **Step 2: 运行新测试，确认通过**

```bash
pytest tests/test_paths.py -v -k "bootstrap"
```

预期：3 个测试 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_paths.py
git commit -m "test(paths): add bootstrap_user_dir tests"
```

---

### Task 3: TDD — `find_config`

**Files:**
- Modify: `tests/test_paths.py`

- [ ] **Step 1: 在 `tests/test_paths.py` 末尾追加 find_config 测试**

```python
def test_find_config_prefers_user_dir(tmp_path, monkeypatch):
    """USER_DIR/config.yaml 存在时优先返回"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    user_dir.mkdir(parents=True)
    user_config = user_dir / "config.yaml"
    user_config.write_text("# user config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    # exe_dir 也有 config（确保 user_dir 优先）
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("# exe config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()
    assert result == user_config


def test_find_config_falls_back_to_exe_dir(tmp_path, monkeypatch):
    """USER_DIR 无 config 时 fallback 到 exe_dir"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"  # 不创建 config.yaml
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("# exe config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()
    assert result == exe_dir / "config.yaml"


def test_find_config_bootstraps_when_neither_exists(tmp_path, monkeypatch):
    """两处均无 config 时触发 bootstrap，返回 USER_DIR/config.yaml"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()  # 不放 config.yaml
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()

    assert result == user_dir / "config.yaml"
    assert result.exists()
    # 确认子目录也被创建
    assert (user_dir / "models").is_dir()
```

- [ ] **Step 2: 运行新测试，确认通过**

```bash
pytest tests/test_paths.py -v -k "find_config"
```

预期：3 个测试 PASS

- [ ] **Step 3: 运行全套 test_paths 测试**

```bash
pytest tests/test_paths.py -v
```

预期：8 个测试全部 PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_paths.py
git commit -m "test(paths): add find_config tests"
```

---

### Task 4: 修改 `core/config.py` — 移除内联 model path 解析

**Files:**
- Modify: `core/config.py`

- [ ] **Step 1: 确认现有 config 测试基线**

```bash
pytest tests/test_config.py -v
```

记录通过数量（应为 4 个），改动后不应减少。

- [ ] **Step 2: 修改 `core/config.py`**

将文件改为以下内容（移除 `Optional` import、移除函数默认值、删除 model path 解析三行）：

```python
# core/config.py
from pathlib import Path
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    path: str = "./models/gemma-4-e2b-instruct.gguf"
    n_gpu_layers: int = -1
    n_threads: int = 6
    n_ctx: int = 4096
    max_tokens: int = 512


class AgentConfig(BaseModel):
    mode: Literal["tool_calling", "code"] = "tool_calling"
    verbose: bool = False
    show_thinking: bool = True


class WebSearchConfig(BaseModel):
    enabled: bool = True
    tavily_api_key: str = ""


class FileManagerConfig(BaseModel):
    enabled: bool = True
    allow_destructive: bool = False
    allowed_dirs: List[str] = Field(default_factory=list)


class SystemInfoConfig(BaseModel):
    enabled: bool = True


class ToolsConfig(BaseModel):
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    file_manager: FileManagerConfig = Field(default_factory=FileManagerConfig)
    system_info: SystemInfoConfig = Field(default_factory=SystemInfoConfig)


class RuntimeConfig(BaseModel):
    language: str = "zh"
    log_level: str = "info"


class AppConfig(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


def load_config(config_path: Path) -> AppConfig:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)
    return AppConfig()
```

- [ ] **Step 3: 运行 config 测试**

```bash
pytest tests/test_config.py -v
```

预期：4 个测试全部 PASS

- [ ] **Step 4: 提交**

```bash
git add core/config.py
git commit -m "refactor(config): remove inline model path resolution, make config_path required"
```

---

### Task 5: 修改 `main.py` — 使用 `find_config` + `resolve_relative`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 修改 `main.py` 的 config 加载块**

将 `main()` 函数开头的 config 加载部分（第 12–21 行）替换为：

```python
def main() -> None:
    # ── 1. Load config ────────────────────────────────────────────────────────
    from core.paths import find_config, resolve_relative
    from core.config import load_config
    config_path = find_config()
    config = load_config(config_path)
    config.model.path = str(resolve_relative(config_path.parent, config.model.path))
```

删除原来的 `if not config_path.exists(): console.print(...)` 警告块（第 17–21 行）。完整修改后 `main.py`：

```python
# main.py
import sys
import time
from pathlib import Path

from ui.console import console

__version__ = "0.1.0"


def main() -> None:
    # ── 1. Load config ────────────────────────────────────────────────────────
    from core.paths import find_config, resolve_relative
    from core.config import load_config
    config_path = find_config()
    config = load_config(config_path)
    config.model.path = str(resolve_relative(config_path.parent, config.model.path))

    # ── 2. Load tools ─────────────────────────────────────────────────────────
    from tools.registry import ToolRegistry
    tools = ToolRegistry(config.tools).load()

    # ── 3. Load model ─────────────────────────────────────────────────────────
    model_path = config.model.path
    console.print(f"[bold]正在加载模型:[/] {model_path} ...")

    # Set up file logging before model load so llama.cpp's C-level stderr
    # (fd 2) is redirected to the log file and stays off the terminal.
    from ui.logger import setup as setup_logging
    log_file = setup_logging(config.runtime.log_level)
    console.print(f"[dim]日志写入: {log_file}[/]")

    t0 = time.perf_counter()
    from core.model import LlamaCppBackend
    backend = LlamaCppBackend(config.model)
    try:
        backend.load()
    except Exception as e:
        console.print(f"[red]模型加载失败: {e}[/]")
        console.print("请检查 config.yaml 中的 model.path 是否指向有效的 .gguf 文件。")
        sys.exit(1)

    elapsed = time.perf_counter() - t0
    mem_gb = backend.get_memory_usage_gb()
    console.print(
        f"[green]模型加载完成[/] ({elapsed:.1f}s) | "
        f"内存占用: {mem_gb:.1f}GB | "
        f"工具: {len(tools)} 个已启用"
    )

    # ── 4. Create agent ───────────────────────────────────────────────────────
    from core.agent import create_agent_runner
    smolagents_model = backend.to_smolagents_model()
    agent = create_agent_runner(config.agent, smolagents_model, tools)

    # ── 5. Start CLI ──────────────────────────────────────────────────────────
    from cli.app import run_cli
    run_cli(agent, config, tools)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 手动验证（首次运行 bootstrap 场景）**

若 `~\.pheobe\MicroAgent\config.yaml` 不存在，运行：

```bash
python main.py
```

预期：
1. 无报错地自动创建 `~\.pheobe\MicroAgent\{models,memory,logs,skills}\` 目录
2. 写入 `~\.pheobe\MicroAgent\config.yaml`（内容为内置默认模板）
3. 因 model 文件不存在，打印 `[red]模型加载失败[/]` 后退出（正常，非 bug）

- [ ] **Step 3: 提交**

```bash
git add main.py
git commit -m "refactor(main): use find_config + resolve_relative from core.paths"
```

---

### Task 6: 修改 `ui/logger.py` — 替换 `_log_dir()`

**Files:**
- Modify: `ui/logger.py`

- [ ] **Step 1: 修改 `ui/logger.py`**

删除 `_log_dir()` 函数，添加 `from core.paths import log_dir`，修改 `setup()` 调用：

```python
# ui/logger.py
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from core.paths import log_dir

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHF]')


class _FileStream:
    """File-only stream — never writes to the terminal."""

    def __init__(self, path: Path) -> None:
        self._f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        return self._f.write(_ANSI_RE.sub('', text))

    def flush(self) -> None:
        self._f.flush()

    def fileno(self) -> int:
        return self._f.fileno()

    @property
    def encoding(self) -> str:
        return "utf-8"

    def isatty(self) -> bool:
        return False


def setup(log_level: str = "info") -> Path:
    """Set up file-based logging.

    Must be called AFTER ui.console is imported (so our Rich Console already
    captured the real stdout) but BEFORE the smolagents agent is created (so
    smolagents' internal Rich Console picks up the redirected stdout and writes
    to the log file instead of the terminal).

    Returns the log file path.
    """
    log_file = log_dir() / f"microagent_{datetime.now():%Y-%m-%d}.log"

    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    stream = _FileStream(log_file)
    sys.stdout = stream  # type: ignore[assignment]
    sys.stderr = stream  # type: ignore[assignment]

    # Also redirect the OS-level file descriptor 2 (C-library stderr) to the
    # log file, so llama.cpp diagnostic messages don't appear in the terminal.
    _fd = os.open(str(log_file), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
    os.dup2(_fd, 2)
    os.close(_fd)

    return log_file
```

- [ ] **Step 2: 运行全套测试**

```bash
pytest tests/ -v
```

预期：所有测试通过

- [ ] **Step 3: 提交**

```bash
git add ui/logger.py
git commit -m "refactor(logger): replace _log_dir() with import from core.paths"
```

---

## Self-Review

**1. Spec coverage：**

| Spec 要求 | 对应 Task |
|---|---|
| `core/paths.py` — `USER_DIR`, `get_exe_dir()` | Task 1 |
| `resolve_relative()` 绝对直通 + 相对解析 | Task 1 |
| `bootstrap_user_dir()` 创建目录树 + 写/复制 config | Task 2 |
| `find_config()` 三步查找 + 自动 bootstrap | Task 1 + Task 3 |
| `log_dir()` | Task 1 |
| `core/config.py` 移除 model path 解析 | Task 4 |
| `main.py` 替换 config_path 逻辑 | Task 5 |
| `ui/logger.py` 替换 `_log_dir()` | Task 6 |
| 错误处理：PermissionError → print + exit | Task 1（bootstrap 内含） |
| 错误处理：bootstrap template 复制失败 → 降级写默认 | Task 1（bootstrap 内含） |
| 全部 8 个测试场景 | Tasks 1–3 |

**2. Placeholder scan：** 无 TBD/TODO，无模糊表述，所有代码步骤均含完整实现。

**3. Type consistency：**
- `find_config() -> Path` — Task 1 实现、Task 3 测试一致
- `bootstrap_user_dir(template: Path | None = None) -> Path` — Task 1 实现、Task 2 测试一致
- `resolve_relative(config_dir: Path, value: str) -> Path` — Task 1 实现、Task 1 测试一致
- `log_dir() -> Path` — Task 1 实现、Task 6 调用方式一致
