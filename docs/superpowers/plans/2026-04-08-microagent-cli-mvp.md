# MicroAgent CLI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可独立运行的本地 AI Agent CLI，基于 smolagents + llama-cpp-python，支持文件管理、网络搜索、系统信息查询，最终打包为单一 `.exe` 文件。

**Architecture:** `main.py` 负责引导（加载配置 → 实例化模型 → 注册工具 → 启动 CLI）。`core/` 层通过抽象类隔离 Agent 模式和模型后端，使未来升级不影响上层。`tools/` 层每个 Tool 是独立的 smolagents Tool 子类，通过 `ToolRegistry` 统一注册。

**Tech Stack:** Python 3.11+, smolagents, llama-cpp-python (Vulkan), rich, psutil, pydantic v2, pyyaml, duckduckgo-search, tavily-python, pytest, Nuitka

---

## 文件结构总览

```
MicroAgent/
├── core/
│   ├── __init__.py
│   ├── agent.py          # AgentRunner ABC + ToolCallingAgentRunner + CodeAgentRunner
│   ├── config.py         # Pydantic models + load_config()
│   └── model.py          # ModelBackend ABC + LlamaCppBackend
├── tools/
│   ├── __init__.py
│   ├── base.py           # MicroTool(Tool) 基类
│   ├── file_manager.py   # 9 个文件系统 Tool 类 + create_file_manager_tools()
│   ├── registry.py       # ToolRegistry.load() → List[Tool]
│   ├── system_info.py    # SystemInfoTool
│   └── web_search.py     # WebSearchTool（DuckDuckGo/Tavily 自动切换）
├── cli/
│   ├── __init__.py
│   └── app.py            # run_cli() 主循环
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_agent.py
│   ├── test_model.py
│   └── tools/
│       ├── __init__.py
│       ├── test_file_manager.py
│       ├── test_registry.py
│       ├── test_system_info.py
│       └── test_web_search.py
├── config.yaml           # 默认用户配置（带注释）
├── main.py               # 入口
├── requirements.txt
├── requirements-dev.txt
└── build.bat             # Nuitka 一键打包脚本
```

---

## Task 1: 项目脚手架

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `core/__init__.py`, `tools/__init__.py`, `cli/__init__.py`, `tests/__init__.py`, `tests/tools/__init__.py`
- Create: `main.py`（占位版，仅打印版本）

- [ ] **Step 1: 创建依赖文件**

`requirements.txt`:
```
smolagents>=0.3.0
llama-cpp-python>=0.2.90
rich>=13.7.0
psutil>=5.9.0
pydantic>=2.6.0
pyyaml>=6.0.1
duckduckgo-search>=6.2.0
tavily-python>=0.3.3
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.1.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: 创建目录结构和空 `__init__.py`**

```bash
mkdir -p core tools cli tests/tools
touch core/__init__.py tools/__init__.py cli/__init__.py tests/__init__.py tests/tools/__init__.py
```

- [ ] **Step 3: 创建占位 `main.py`**

```python
# main.py
__version__ = "0.1.0"

def main() -> None:
    print(f"MicroAgent v{__version__}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证可运行**

```bash
python main.py
```
Expected output: `MicroAgent v0.1.0`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt core/__init__.py tools/__init__.py cli/__init__.py tests/__init__.py tests/tools/__init__.py main.py
git commit -m "chore: project scaffold with dependencies and directory structure"
```

---

## Task 2: 配置系统

**Files:**
- Create: `core/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from core.config import load_config, AppConfig


def test_defaults_when_file_missing():
    config = load_config(Path("/nonexistent/config.yaml"))
    assert isinstance(config, AppConfig)
    assert config.model.n_threads == 6
    assert config.model.n_gpu_layers == -1
    assert config.model.n_ctx == 4096
    assert config.model.max_tokens == 512
    assert config.agent.mode == "tool_calling"
    assert config.agent.verbose is True
    assert config.tools.file_manager.allow_destructive is False
    assert config.tools.file_manager.allowed_dirs == []
    assert config.tools.web_search.tavily_api_key == ""
    assert config.runtime.language == "zh"


def test_yaml_overrides_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model:\n  n_threads: 4\nagent:\n  verbose: false\n", encoding="utf-8")
    config = load_config(cfg)
    assert config.model.n_threads == 4
    assert config.agent.verbose is False
    assert config.model.n_gpu_layers == -1  # default preserved


def test_invalid_agent_mode_raises(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("agent:\n  mode: unknown_mode\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(cfg)


def test_allowed_dirs_parsed(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "tools:\n  file_manager:\n    allow_destructive: true\n    allowed_dirs:\n      - /tmp\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.tools.file_manager.allow_destructive is True
    assert config.tools.file_manager.allowed_dirs == ["/tmp"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_config.py -v
```
Expected: `ImportError: cannot import name 'load_config' from 'core.config'`

- [ ] **Step 3: 实现 `core/config.py`**

```python
# core/config.py
from pathlib import Path
from typing import List, Literal, Optional

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
    verbose: bool = True


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


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    if config_path is None:
        import sys
        config_path = Path(sys.argv[0]).parent / "config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_config.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py
git commit -m "feat: config system with pydantic validation and YAML loading"
```

---

## Task 3: Tool 基类与 ToolRegistry

**Files:**
- Create: `tools/base.py`
- Create: `tools/registry.py`
- Create: `tests/tools/test_registry.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/tools/test_registry.py
from unittest.mock import MagicMock, patch
from core.config import ToolsConfig, WebSearchConfig, FileManagerConfig, SystemInfoConfig
from tools.registry import ToolRegistry


def test_all_enabled_loads_three_groups():
    config = ToolsConfig()
    mock_tool = MagicMock()

    with (
        patch("tools.web_search.WebSearchTool", return_value=mock_tool),
        patch("tools.file_manager.create_file_manager_tools", return_value=[mock_tool, mock_tool]),
        patch("tools.system_info.SystemInfoTool", return_value=mock_tool),
    ):
        tools = ToolRegistry(config).load()

    assert len(tools) == 4  # 1 web + 2 file_manager + 1 system_info


def test_disabled_tools_are_excluded():
    config = ToolsConfig(
        web_search=WebSearchConfig(enabled=False),
        system_info=SystemInfoConfig(enabled=False),
    )
    mock_tool = MagicMock()

    with patch("tools.file_manager.create_file_manager_tools", return_value=[mock_tool]):
        tools = ToolRegistry(config).load()

    assert len(tools) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/tools/test_registry.py -v
```
Expected: `ImportError: cannot import name 'ToolRegistry'`

- [ ] **Step 3: 实现 `tools/base.py` 和 `tools/registry.py`**

```python
# tools/base.py
from smolagents import Tool


class MicroTool(Tool):
    """Base class for all MicroAgent tools.
    Subclasses must define: name, description, inputs, output_type, forward().
    """
    pass
```

```python
# tools/registry.py
from typing import List

from smolagents import Tool

from core.config import ToolsConfig


class ToolRegistry:
    def __init__(self, config: ToolsConfig) -> None:
        self._config = config

    def load(self) -> List[Tool]:
        tools: List[Tool] = []

        if self._config.web_search.enabled:
            from tools.web_search import WebSearchTool
            tools.append(WebSearchTool(self._config.web_search.tavily_api_key))

        if self._config.file_manager.enabled:
            from tools.file_manager import create_file_manager_tools
            tools.extend(create_file_manager_tools(self._config.file_manager))

        if self._config.system_info.enabled:
            from tools.system_info import SystemInfoTool
            tools.append(SystemInfoTool())

        return tools
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/tools/test_registry.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/base.py tools/registry.py tests/tools/test_registry.py
git commit -m "feat: tool base class and registry with lazy loading"
```

---

## Task 4: SystemInfo 工具

**Files:**
- Create: `tools/system_info.py`
- Create: `tests/tools/test_system_info.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/tools/test_system_info.py
from unittest.mock import MagicMock, patch
from tools.system_info import SystemInfoTool


def test_system_info_returns_string():
    tool = SystemInfoTool()
    mock_battery = MagicMock()
    mock_battery.percent = 80.0
    mock_battery.power_plugged = True
    mock_mem = MagicMock()
    mock_mem.used = 4 * 1024 ** 3
    mock_mem.total = 16 * 1024 ** 3
    mock_mem.percent = 25.0

    with (
        patch("psutil.cpu_percent", return_value=15.0),
        patch("psutil.virtual_memory", return_value=mock_mem),
        patch("psutil.sensors_battery", return_value=mock_battery),
    ):
        result = tool.forward()

    assert "15.0%" in result
    assert "4.0GB" in result
    assert "16.0GB" in result
    assert "80%" in result
    assert "充电" in result


def test_system_info_no_battery():
    tool = SystemInfoTool()
    mock_mem = MagicMock()
    mock_mem.used = 2 * 1024 ** 3
    mock_mem.total = 16 * 1024 ** 3
    mock_mem.percent = 12.5

    with (
        patch("psutil.cpu_percent", return_value=5.0),
        patch("psutil.virtual_memory", return_value=mock_mem),
        patch("psutil.sensors_battery", return_value=None),
    ):
        result = tool.forward()

    assert "未检测到" in result
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/tools/test_system_info.py -v
```
Expected: `ImportError: cannot import name 'SystemInfoTool'`

- [ ] **Step 3: 实现 `tools/system_info.py`**

```python
# tools/system_info.py
import psutil

from tools.base import MicroTool


class SystemInfoTool(MicroTool):
    name = "system_info"
    description = "获取当前系统状态，包括CPU使用率、内存占用和电池状态。无需输入参数。"
    inputs = {}
    output_type = "string"

    def forward(self) -> str:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        lines = [
            f"CPU使用率: {cpu}%",
            f"内存: {mem.used / (1024 ** 3):.1f}GB / {mem.total / (1024 ** 3):.1f}GB ({mem.percent}%)",
        ]

        if battery:
            status = "正在充电" if battery.power_plugged else "未充电"
            lines.append(f"电池: {battery.percent:.0f}%，{status}")
        else:
            lines.append("电池: 未检测到")

        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/tools/test_system_info.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/system_info.py tests/tools/test_system_info.py
git commit -m "feat: system_info tool reporting CPU, memory, and battery"
```

---

## Task 5: FileManager 只读工具

**Files:**
- Create: `tools/file_manager.py`（只读部分）
- Create: `tests/tools/test_file_manager.py`（只读测试）

- [ ] **Step 1: 写失败的测试**

```python
# tests/tools/test_file_manager.py
import pytest
from pathlib import Path
from tools.file_manager import (
    ListDirectoryTool,
    ReadFileTool,
    GetFileInfoTool,
    FindFilesTool,
)


def test_list_directory(tmp_path):
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    tool = ListDirectoryTool()
    result = tool.forward(str(tmp_path))
    assert "file.txt" in result
    assert "subdir" in result


def test_list_directory_not_found():
    tool = ListDirectoryTool()
    result = tool.forward("/nonexistent/path")
    assert "不存在" in result


def test_list_directory_not_a_dir(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    tool = ListDirectoryTool()
    result = tool.forward(str(f))
    assert "不是目录" in result


def test_read_file(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world", encoding="utf-8")
    tool = ReadFileTool()
    result = tool.forward(str(f))
    assert result == "hello world"


def test_read_file_not_found():
    tool = ReadFileTool()
    result = tool.forward("/nonexistent/file.txt")
    assert "不存在" in result


def test_get_file_info(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("abc")
    tool = GetFileInfoTool()
    result = tool.forward(str(f))
    assert "test.txt" in result
    assert "字节" in result


def test_find_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("")
    tool = FindFilesTool()
    result = tool.forward(str(tmp_path), "*.py")
    assert "a.py" in result
    assert "c.py" in result
    assert "b.txt" not in result


def test_find_files_no_match(tmp_path):
    tool = FindFilesTool()
    result = tool.forward(str(tmp_path), "*.xyz")
    assert "未找到" in result
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/tools/test_file_manager.py -v
```
Expected: `ImportError: cannot import name 'ListDirectoryTool'`

- [ ] **Step 3: 实现只读工具（`tools/file_manager.py` 第一部分）**

```python
# tools/file_manager.py
from pathlib import Path
from typing import List

from tools.base import MicroTool
from core.config import FileManagerConfig


# ─── Read-only tools ────────────────────────────────────────────────────────


class ListDirectoryTool(MicroTool):
    name = "list_directory"
    description = "列出指定目录下的文件和子目录。"
    inputs = {"path": {"type": "string", "description": "要列出内容的目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：路径不存在: {path}"
        if not p.is_dir():
            return f"错误：{path} 不是目录"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        if not items:
            return f"{path} (空目录)"
        lines = [f"[DIR]  {i.name}" if i.is_dir() else f"[FILE] {i.name}" for i in items]
        return f"{path} ({len(items)} 项):\n" + "\n".join(lines)


class ReadFileTool(MicroTool):
    name = "read_file"
    description = "读取文本文件的完整内容并返回。"
    inputs = {"path": {"type": "string", "description": "要读取的文件路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：文件不存在: {path}"
        if not p.is_file():
            return f"错误：{path} 不是文件"
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"错误：无法读取文件: {e}"


class GetFileInfoTool(MicroTool):
    name = "get_file_info"
    description = "获取文件或目录的元信息，包括大小、修改时间、类型。"
    inputs = {"path": {"type": "string", "description": "要查询的文件或目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：路径不存在: {path}"
        stat = p.stat()
        import datetime
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        kind = "目录" if p.is_dir() else "文件"
        return (
            f"名称: {p.name}\n"
            f"类型: {kind}\n"
            f"大小: {stat.st_size} 字节\n"
            f"修改时间: {mtime}"
        )


class FindFilesTool(MicroTool):
    name = "find_files"
    description = "在指定目录下递归搜索匹配文件名模式的文件（支持通配符，如 *.py）。"
    inputs = {
        "directory": {"type": "string", "description": "搜索的根目录"},
        "pattern": {"type": "string", "description": "文件名匹配模式，如 *.txt 或 *.py"},
    }
    output_type = "string"

    def forward(self, directory: str, pattern: str) -> str:
        p = Path(directory)
        if not p.exists():
            return f"错误：目录不存在: {directory}"
        matches = sorted(p.rglob(pattern))
        if not matches:
            return f"未找到匹配 '{pattern}' 的文件"
        lines = [str(m.relative_to(p)) for m in matches]
        return f"找到 {len(matches)} 个匹配文件:\n" + "\n".join(lines)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/tools/test_file_manager.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/file_manager.py tests/tools/test_file_manager.py
git commit -m "feat: file_manager read-only tools (list, read, info, find)"
```

---

## Task 6: FileManager 破坏性工具

**Files:**
- Modify: `tools/file_manager.py`（追加破坏性工具 + `create_file_manager_tools`）
- Modify: `tests/tools/test_file_manager.py`（追加破坏性工具测试）

- [ ] **Step 1: 写失败的测试**

在 `tests/tools/test_file_manager.py` 末尾追加：

```python
from tools.file_manager import (
    WriteFileTool,
    AppendFileTool,
    CreateDirectoryTool,
    MoveFileTool,
    DeleteFileTool,
    create_file_manager_tools,
)
from core.config import FileManagerConfig


# ─── Destructive tools ──────────────────────────────────────────────────────


def test_write_file(tmp_path):
    tool = WriteFileTool(allowed_dirs=[])
    path = str(tmp_path / "out.txt")
    result = tool.forward(path, "hello")
    assert "成功" in result
    assert Path(path).read_text(encoding="utf-8") == "hello"


def test_write_file_respects_allowed_dirs(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool = WriteFileTool(allowed_dirs=[str(allowed)])
    result = tool.forward(str(other / "x.txt"), "data")
    assert "不在允许" in result


def test_append_file(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("line1\n", encoding="utf-8")
    tool = AppendFileTool(allowed_dirs=[])
    tool.forward(str(f), "line2\n")
    assert f.read_text(encoding="utf-8") == "line1\nline2\n"


def test_create_directory(tmp_path):
    tool = CreateDirectoryTool(allowed_dirs=[])
    new_dir = str(tmp_path / "a" / "b" / "c")
    result = tool.forward(new_dir)
    assert "成功" in result
    assert Path(new_dir).is_dir()


def test_move_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("data")
    dst = str(tmp_path / "dst.txt")
    tool = MoveFileTool(allowed_dirs=[])
    result = tool.forward(str(src), dst)
    assert "成功" in result
    assert not src.exists()
    assert Path(dst).read_text() == "data"


def test_delete_file(tmp_path):
    f = tmp_path / "del.txt"
    f.write_text("x")
    tool = DeleteFileTool(allowed_dirs=[])
    result = tool.forward(str(f))
    assert "成功" in result
    assert not f.exists()


def test_delete_file_refuses_directory(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    tool = DeleteFileTool(allowed_dirs=[])
    result = tool.forward(str(d))
    assert "不是文件" in result


def test_create_file_manager_tools_readonly():
    config = FileManagerConfig(allow_destructive=False)
    tools = create_file_manager_tools(config)
    names = [t.name for t in tools]
    assert "list_directory" in names
    assert "read_file" in names
    assert "write_file" not in names
    assert "delete_file" not in names


def test_create_file_manager_tools_destructive():
    config = FileManagerConfig(allow_destructive=True)
    tools = create_file_manager_tools(config)
    names = [t.name for t in tools]
    assert "write_file" in names
    assert "delete_file" in names
```

- [ ] **Step 2: 运行测试，确认新增测试失败**

```bash
pytest tests/tools/test_file_manager.py -v
```
Expected: `ImportError: cannot import name 'WriteFileTool'`

- [ ] **Step 3: 追加破坏性工具到 `tools/file_manager.py`**

在文件末尾追加：

```python
# ─── Destructive tools ────────────────────────────────────────────────────────


class _DestructiveTool(MicroTool):
    """Mixin for tools that check allowed_dirs before operating."""

    def __init__(self, allowed_dirs: List[str]) -> None:
        super().__init__()
        self._allowed = [Path(d).resolve() for d in allowed_dirs] if allowed_dirs else []

    def _check_allowed(self, path: Path) -> bool:
        if not self._allowed:
            return True
        resolved = path.resolve()
        return any(resolved == d or d in resolved.parents for d in self._allowed)

    def _guard(self, path: Path) -> str | None:
        if not self._check_allowed(path):
            return f"错误：路径 {path} 不在允许的目录范围内"
        return None


class WriteFileTool(_DestructiveTool):
    name = "write_file"
    description = "将内容写入文件（会覆盖已有内容）。需要 allow_destructive: true。"
    inputs = {
        "path": {"type": "string", "description": "目标文件路径"},
        "content": {"type": "string", "description": "要写入的文本内容"},
    }
    output_type = "string"

    def forward(self, path: str, content: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"成功写入 {len(content)} 字符到 {path}"


class AppendFileTool(_DestructiveTool):
    name = "append_file"
    description = "向已有文件末尾追加内容。需要 allow_destructive: true。"
    inputs = {
        "path": {"type": "string", "description": "目标文件路径"},
        "content": {"type": "string", "description": "要追加的文本内容"},
    }
    output_type = "string"

    def forward(self, path: str, content: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"成功追加 {len(content)} 字符到 {path}"


class CreateDirectoryTool(_DestructiveTool):
    name = "create_directory"
    description = "创建目录（包含所有中间目录，等效于 mkdir -p）。需要 allow_destructive: true。"
    inputs = {"path": {"type": "string", "description": "要创建的目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        p.mkdir(parents=True, exist_ok=True)
        return f"成功创建目录: {path}"


class MoveFileTool(_DestructiveTool):
    name = "move_file"
    description = "移动或重命名文件。需要 allow_destructive: true。"
    inputs = {
        "src": {"type": "string", "description": "源文件路径"},
        "dst": {"type": "string", "description": "目标路径"},
    }
    output_type = "string"

    def forward(self, src: str, dst: str) -> str:
        s, d = Path(src), Path(dst)
        if err := self._guard(s):
            return err
        if not s.exists():
            return f"错误：源文件不存在: {src}"
        s.rename(d)
        return f"成功移动 {src} -> {dst}"


class DeleteFileTool(_DestructiveTool):
    name = "delete_file"
    description = "删除单个文件（不删除目录）。需要 allow_destructive: true。"
    inputs = {"path": {"type": "string", "description": "要删除的文件路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        if not p.exists():
            return f"错误：文件不存在: {path}"
        if not p.is_file():
            return f"错误：{path} 不是文件（拒绝删除目录）"
        p.unlink()
        return f"成功删除: {path}"


# ─── Factory ─────────────────────────────────────────────────────────────────


def create_file_manager_tools(config: FileManagerConfig) -> List[MicroTool]:
    read_tools: List[MicroTool] = [
        ListDirectoryTool(),
        ReadFileTool(),
        GetFileInfoTool(),
        FindFilesTool(),
    ]
    if not config.allow_destructive:
        return read_tools

    destructive_tools: List[MicroTool] = [
        WriteFileTool(config.allowed_dirs),
        AppendFileTool(config.allowed_dirs),
        CreateDirectoryTool(config.allowed_dirs),
        MoveFileTool(config.allowed_dirs),
        DeleteFileTool(config.allowed_dirs),
    ]
    return read_tools + destructive_tools
```

- [ ] **Step 4: 运行全部 file_manager 测试，确认通过**

```bash
pytest tests/tools/test_file_manager.py -v
```
Expected: `19 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/file_manager.py tests/tools/test_file_manager.py
git commit -m "feat: file_manager destructive tools with allowed_dirs guard"
```

---

## Task 7: WebSearch 工具

**Files:**
- Create: `tools/web_search.py`
- Create: `tests/tools/test_web_search.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/tools/test_web_search.py
from unittest.mock import MagicMock, patch
from tools.web_search import WebSearchTool


def test_uses_duckduckgo_when_no_key():
    tool = WebSearchTool(tavily_api_key="")
    mock_results = [
        {"title": "Result 1", "href": "https://example.com/1", "body": "Content 1"},
        {"title": "Result 2", "href": "https://example.com/2", "body": "Content 2"},
    ]
    with patch("tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.__enter__ = lambda s: s
        mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.return_value.text.return_value = mock_results
        result = tool.forward("test query")

    assert "Result 1" in result
    assert "https://example.com/1" in result


def test_uses_tavily_when_key_provided():
    tool = WebSearchTool(tavily_api_key="fake-key")
    mock_response = {
        "results": [
            {"title": "Tavily Result", "url": "https://tavily.com/1", "content": "Tavily Content"},
        ]
    }
    with patch("tools.web_search.TavilyClient") as mock_cls:
        mock_cls.return_value.search.return_value = mock_response
        result = tool.forward("test query")

    assert "Tavily Result" in result
    assert "https://tavily.com/1" in result


def test_empty_results_message():
    tool = WebSearchTool(tavily_api_key="")
    with patch("tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.__enter__ = lambda s: s
        mock_ddgs.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.return_value.text.return_value = []
        result = tool.forward("query with no results")

    assert "未找到" in result
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/tools/test_web_search.py -v
```
Expected: `ImportError: cannot import name 'WebSearchTool'`

- [ ] **Step 3: 实现 `tools/web_search.py`**

```python
# tools/web_search.py
from tools.base import MicroTool


class WebSearchTool(MicroTool):
    name = "web_search"
    description = "搜索网络并返回相关结果摘要。提供搜索关键词或完整问题。"
    inputs = {"query": {"type": "string", "description": "搜索关键词或问题"}}
    output_type = "string"

    def __init__(self, tavily_api_key: str = "") -> None:
        super().__init__()
        self._use_tavily = bool(tavily_api_key)
        if self._use_tavily:
            from tavily import TavilyClient
            self._tavily = TavilyClient(api_key=tavily_api_key)

    def forward(self, query: str) -> str:
        if self._use_tavily:
            return self._search_tavily(query)
        return self._search_duckduckgo(query)

    def _search_tavily(self, query: str) -> str:
        from tavily import TavilyClient  # noqa: F401 (used in __init__)
        response = self._tavily.search(query, max_results=5)
        results = response.get("results", [])
        if not results:
            return "未找到相关结果"
        lines = [
            f"{i + 1}. {r['title']}\n   {r['url']}\n   {r['content'][:200]}"
            for i, r in enumerate(results)
        ]
        return "\n\n".join(lines)

    def _search_duckduckgo(self, query: str) -> str:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "未找到相关结果"
        lines = [
            f"{i + 1}. {r['title']}\n   {r['href']}\n   {r['body'][:200]}"
            for i, r in enumerate(results)
        ]
        return "\n\n".join(lines)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/tools/test_web_search.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/web_search.py tests/tools/test_web_search.py
git commit -m "feat: web_search tool with DuckDuckGo default and Tavily upgrade path"
```

---

## Task 8: ModelBackend

**Files:**
- Create: `core/model.py`
- Create: `tests/test_model.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_model.py
from unittest.mock import MagicMock, patch
from core.config import ModelConfig
from core.model import LlamaCppBackend


def test_load_calls_llama_with_correct_params():
    config = ModelConfig(
        path="./model.gguf",
        n_gpu_layers=-1,
        n_threads=6,
        n_ctx=4096,
    )
    with patch("core.model.Llama") as mock_llama:
        backend = LlamaCppBackend(config)
        backend.load()
        mock_llama.assert_called_once_with(
            model_path="./model.gguf",
            n_gpu_layers=-1,
            n_threads=6,
            n_ctx=4096,
            verbose=False,
        )


def test_to_smolagents_model_returns_wrapped_model():
    config = ModelConfig()
    with patch("core.model.Llama") as mock_llama:
        mock_instance = MagicMock()
        mock_llama.return_value = mock_instance
        backend = LlamaCppBackend(config)
        backend.load()

    with patch("core.model.LlamaCppModel") as mock_wrapper:
        mock_wrapper.return_value = MagicMock()
        result = backend.to_smolagents_model()
        mock_wrapper.assert_called_once_with(mock_instance, max_new_tokens=config.max_tokens)
        assert result is mock_wrapper.return_value


def test_get_memory_usage_returns_float():
    config = ModelConfig()
    backend = LlamaCppBackend(config)
    with patch("psutil.Process") as mock_proc:
        mock_proc.return_value.memory_info.return_value.rss = 2 * 1024 ** 3
        usage = backend.get_memory_usage_gb()
    assert abs(usage - 2.0) < 0.01
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_model.py -v
```
Expected: `ImportError: cannot import name 'LlamaCppBackend'`

- [ ] **Step 3: 实现 `core/model.py`**

```python
# core/model.py
from abc import ABC, abstractmethod
from typing import Any

from core.config import ModelConfig


class ModelBackend(ABC):
    """Abstract backend — swap implementations to change inference engine."""

    @abstractmethod
    def load(self) -> None:
        """Load model into memory. Call once before to_smolagents_model()."""

    @abstractmethod
    def get_memory_usage_gb(self) -> float:
        """Return current process RSS in GB."""

    @abstractmethod
    def to_smolagents_model(self) -> Any:
        """Return a smolagents-compatible model object."""


class LlamaCppBackend(ModelBackend):
    def __init__(self, config: ModelConfig) -> None:
        self._config = config
        self._llm = None

    def load(self) -> None:
        from llama_cpp import Llama
        self._llm = Llama(
            model_path=self._config.path,
            n_gpu_layers=self._config.n_gpu_layers,
            n_threads=self._config.n_threads,
            n_ctx=self._config.n_ctx,
            verbose=False,
        )

    def get_memory_usage_gb(self) -> float:
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)

    def to_smolagents_model(self) -> Any:
        from smolagents import LlamaCppModel
        return LlamaCppModel(self._llm, max_new_tokens=self._config.max_tokens)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_model.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add core/model.py tests/test_model.py
git commit -m "feat: ModelBackend abstraction with LlamaCppBackend implementation"
```

---

## Task 9: AgentRunner

**Files:**
- Create: `core/agent.py`
- Create: `tests/test_agent.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_agent.py
from unittest.mock import MagicMock, patch
from core.config import AgentConfig
from core.agent import create_agent_runner


def test_tool_calling_agent_created_and_runs():
    config = AgentConfig(mode="tool_calling", verbose=False)
    mock_model = MagicMock()
    mock_tools = [MagicMock()]

    with patch("core.agent.ToolCallingAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "the answer"
        runner = create_agent_runner(config, mock_model, mock_tools)
        result = runner.run("what is 2+2?")

    mock_cls.assert_called_once_with(tools=mock_tools, model=mock_model, verbose=False)
    assert result == "the answer"


def test_code_agent_created_when_mode_is_code():
    config = AgentConfig(mode="code", verbose=True)
    mock_model = MagicMock()

    with patch("core.agent.CodeAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "code result"
        runner = create_agent_runner(config, mock_model, [])
        result = runner.run("write a hello world")

    mock_cls.assert_called_once_with(tools=[], model=mock_model, verbose=True)
    assert result == "code result"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_agent.py -v
```
Expected: `ImportError: cannot import name 'create_agent_runner'`

- [ ] **Step 3: 实现 `core/agent.py`**

```python
# core/agent.py
from abc import ABC, abstractmethod
from typing import Any, List

from core.config import AgentConfig


class AgentRunner(ABC):
    """Abstract runner — swap to change agent strategy (tool_calling vs code)."""

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Execute a task and return the final answer."""


class ToolCallingAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool) -> None:
        from smolagents import ToolCallingAgent
        self._agent = ToolCallingAgent(tools=tools, model=model, verbose=verbose)

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


class CodeAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool) -> None:
        from smolagents import CodeAgent
        self._agent = CodeAgent(tools=tools, model=model, verbose=verbose)

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


def create_agent_runner(
    config: AgentConfig, model: Any, tools: List[Any]
) -> AgentRunner:
    if config.mode == "tool_calling":
        return ToolCallingAgentRunner(model, tools, verbose=config.verbose)
    if config.mode == "code":
        return CodeAgentRunner(model, tools, verbose=config.verbose)
    raise ValueError(f"Unknown agent mode: {config.mode!r}")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest tests/test_agent.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add core/agent.py tests/test_agent.py
git commit -m "feat: AgentRunner abstraction supporting tool_calling and code modes"
```

---

## Task 10: CLI 应用

**Files:**
- Create: `cli/app.py`

- [ ] **Step 1: 实现 `cli/app.py`**

（CLI 的核心逻辑是交互式的，用集成测试验证而非单元测试，这里直接实现）

```python
# cli/app.py
from typing import List, Any

from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule

from core.agent import AgentRunner
from core.config import AppConfig

console = Console()

_COMMANDS = {
    "/help": "显示此帮助信息",
    "/tools": "列出已加载的工具及说明",
    "/clear": "清空屏幕",
    "/config": "显示当前配置摘要",
}


def run_cli(agent: AgentRunner, config: AppConfig, tools: List[Any]) -> None:
    _print_header(tools)
    while True:
        try:
            user_input = Prompt.ask("[bold cyan]>[/]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]再见！[/]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_command(user_input, tools, config)
        else:
            _run_task(agent, user_input, verbose=config.agent.verbose)


def _print_header(tools: List[Any]) -> None:
    console.print(Rule("[bold green]MicroAgent[/]"))
    console.print(f"工具已加载: [green]{len(tools)}[/] 个 | 输入 [bold]/help[/] 查看命令，Ctrl+C 退出")
    console.print(Rule())


def _handle_command(cmd: str, tools: List[Any], config: AppConfig) -> None:
    if cmd == "/help":
        for c, desc in _COMMANDS.items():
            console.print(f"  [bold]{c}[/]  {desc}")
    elif cmd == "/tools":
        for tool in tools:
            console.print(f"  [green]+[/] [bold]{tool.name}[/]: {tool.description}")
    elif cmd == "/clear":
        console.clear()
        _print_header(tools)
    elif cmd == "/config":
        console.print_json(config.model_dump_json(indent=2))
    else:
        console.print(f"[red]未知命令: {cmd}[/]。输入 /help 查看可用命令。")


def _run_task(agent: AgentRunner, prompt: str, verbose: bool) -> None:
    try:
        if verbose:
            result = agent.run(prompt)
        else:
            with console.status("[bold]思考中...[/]"):
                result = agent.run(prompt)
        console.print(Rule())
        console.print(f"[bold green]结果:[/] {result}")
        console.print(Rule())
    except Exception as e:
        console.print(f"[red]错误: {e}[/]")
```

- [ ] **Step 2: 手动冒烟测试（暂无模型时跳过）**

检查语法无误：
```bash
python -c "from cli.app import run_cli; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cli/app.py
git commit -m "feat: CLI main loop with rich output and built-in commands"
```

---

## Task 11: 主入口点

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 实现完整 `main.py`**

```python
# main.py
import sys
import time
from pathlib import Path

from rich.console import Console

__version__ = "0.1.0"
console = Console()


def main() -> None:
    # ── 1. Load config ────────────────────────────────────────────────────────
    from core.config import load_config
    config_path = Path(sys.argv[0]).parent / "config.yaml"
    config = load_config(config_path)

    if not Path(config_path).exists():
        console.print(
            "[yellow]提示：未找到 config.yaml，使用默认配置。"
            "可在 exe 同级目录创建 config.yaml 进行自定义。[/]"
        )

    # ── 2. Load tools ─────────────────────────────────────────────────────────
    from tools.registry import ToolRegistry
    tools = ToolRegistry(config.tools).load()

    # ── 3. Load model ─────────────────────────────────────────────────────────
    model_path = config.model.path
    console.print(f"[bold]正在加载模型:[/] {model_path} ...")
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

- [ ] **Step 2: 运行全部测试，确认无回归**

```bash
pytest tests/ -v
```
Expected: all tests pass（约 18+ tests）

- [ ] **Step 3: 语法检查入口**

```bash
python -c "import main; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: main entry point wiring config, model, tools, and CLI"
```

---

## Task 12: 构建脚本与分发文件

**Files:**
- Create: `config.yaml`
- Create: `build.bat`
- Create: `models/.gitkeep`
- Create: `README.txt`

- [ ] **Step 1: 创建默认 `config.yaml`（带完整注释）**

```yaml
# MicroAgent 配置文件
# 将本文件放在 microagent.exe 同级目录

model:
  # GGUF 模型文件路径（相对于本文件，或绝对路径）
  path: ./models/gemma-4-e2b-instruct.gguf
  # GPU 层数：-1 = 全部卸载到 GPU（推荐），0 = 纯 CPU
  n_gpu_layers: -1
  # CPU 推理线程数（建议 4-6，不影响系统其他任务）
  n_threads: 6
  # 上下文长度（token 数）
  n_ctx: 4096
  # 单次最大生成 token 数
  max_tokens: 512

agent:
  # 运行模式：tool_calling（推荐）或 code（需要更强模型）
  mode: tool_calling
  # 是否显示 Agent 推理过程（true = 显示工具调用步骤）
  verbose: true

tools:
  web_search:
    enabled: true
    # Tavily API Key（留空则使用 DuckDuckGo 免费搜索）
    # 申请地址：https://tavily.com
    tavily_api_key: ""

  file_manager:
    enabled: true
    # 是否允许写入/删除/移动操作（默认关闭以防误操作）
    allow_destructive: false
    # 破坏性操作允许的目录白名单（空列表 = 不限制）
    allowed_dirs: []

  system_info:
    enabled: true

runtime:
  # 系统提示语言（zh = 中文，en = 英文）
  language: zh
  log_level: info
```

- [ ] **Step 2: 创建 Nuitka 构建脚本 `build.bat`**

```bat
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
```

- [ ] **Step 3: 创建占位文件和 README**

```bash
mkdir -p models
touch models/.gitkeep
```

`README.txt`:
```
MicroAgent v0.1.0 - 轻量本地 AI Agent
======================================

快速开始：
1. 将 .gguf 模型文件放入 models\ 目录
2. （可选）编辑 config.yaml 配置模型路径和 API Key
3. 双击运行 microagent.exe

系统要求：
- Windows 10/11 x64
- 推荐 16GB 内存
- 支持 Vulkan 的 AMD/NVIDIA GPU（可选，无 GPU 也能运行）

常见问题：
- 模型加载失败：检查 config.yaml 中 model.path 是否正确
- 搜索功能不可用：确认网络连接，或在 config.yaml 配置 tavily_api_key
- 开启文件写入：将 config.yaml 中 allow_destructive 改为 true
```

- [ ] **Step 4: 运行所有测试，最终确认**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add config.yaml build.bat models/.gitkeep README.txt
git commit -m "feat: distribution files - config template, Nuitka build script, README"
```

---

## 自审核对单

**Spec 覆盖检查：**
- [x] 本地 GGUF 模型加载（Task 8）
- [x] n_gpu_layers / n_threads / n_ctx 参数（Task 8）
- [x] 内存占用监控（Task 8, `get_memory_usage_gb`）
- [x] web_search: DuckDuckGo 默认 + Tavily 升级（Task 7）
- [x] file_manager: 9 个工具 + 权限矩阵（Task 5, 6）
- [x] system_info: CPU / 内存 / 电池（Task 4）
- [x] ToolCallingAgent + CodeAgent 扩展点（Task 9）
- [x] ModelBackend 抽象层（Task 8）
- [x] pydantic 配置校验（Task 2）
- [x] YAML 配置，exe 同级目录默认查找（Task 2, 12）
- [x] rich CLI + /help /tools /clear /config（Task 10）
- [x] verbose 默认 true（Task 2, 10）
- [x] Nuitka 打包脚本（Task 12）
- [x] 分发结构说明（Task 12）
