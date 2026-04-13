# Agent Loop 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 smolagents，实现自己的 Plan-then-Execute Agent Loop，彻底解决模型输出格式污染问题。

**Architecture:** Planner 调模型一次产出结构化计划，Executor 纯 Python 执行工具收集 Observation，Synthesizer 调模型汇总答案（支持追加工具调用）。所有 prompt 完全由我们控制，只使用 Gemma native tool call 格式。

**Tech Stack:** Python 3.11+, llama-cpp-python, pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-agent-loop-design.md`

---

## 文件结构

**新建：**
- `core/loop/__init__.py`
- `core/loop/types.py` — Step / Observation / SynthContext dataclass
- `core/loop/parser.py` — Gemma native 格式解析器（从 model.py 迁移）
- `core/loop/prompt.py` — 所有 prompt 模板
- `core/loop/planner.py` — Planner
- `core/loop/executor.py` — Executor
- `core/loop/synthesizer.py` — Synthesizer
- `tests/test_loop/__init__.py`
- `tests/test_loop/test_types.py`
- `tests/test_loop/test_parser.py`
- `tests/test_loop/test_planner.py`
- `tests/test_loop/test_executor.py`
- `tests/test_loop/test_synthesizer.py`

**重写：**
- `tools/base.py` — Tool ABC（移除 smolagents 依赖）
- `tools/web_search.py` — 继承新 Tool ABC
- `tools/file_manager.py` — 继承新 Tool ABC
- `tools/system_info.py` — 继承新 Tool ABC
- `tools/registry.py` — 移除 smolagents.Tool 引用
- `core/agent.py` — AgentRunner ABC + PlanExecuteRunner
- `core/model.py` — 移除 smolagents Model 包装层，提供简单 generate() 接口
- `core/config.py` — AgentConfig 新增字段
- `main.py` — 更新初始化流程

**删除：**
- `tools/think.py`

---

## Task 1: Tool ABC（移除 smolagents 依赖）

**Files:**
- Modify: `tools/base.py`
- Modify: `tools/web_search.py`
- Modify: `tools/file_manager.py`
- Modify: `tools/system_info.py`
- Modify: `tools/registry.py`
- Delete: `tools/think.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tools/test_base.py`：

```python
# tests/test_tools/test_base.py
from tools.base import Tool, ToolParam


def test_tool_param_defaults():
    p = ToolParam(name="query", type="str", description="搜索词")
    assert p.required is True


def test_tool_describe():
    class EchoTool(Tool):
        name = "echo"
        description = "回显输入"
        parameters = [ToolParam("text", "str", "要回显的文本")]

        def __call__(self, **kwargs) -> str:
            return kwargs.get("text", "")

    t = EchoTool()
    desc = t.describe()
    assert "echo(text: str)" in desc
    assert "回显输入" in desc


def test_tool_optional_param_describe():
    class OptTool(Tool):
        name = "opt"
        description = "可选参数工具"
        parameters = [ToolParam("n", "int", "数量", required=False)]

        def __call__(self, **kwargs) -> str:
            return str(kwargs.get("n", 0))

    t = OptTool()
    assert "(可选)" in t.describe()


def test_tool_call():
    class AddTool(Tool):
        name = "add"
        description = "加法"
        parameters = [
            ToolParam("a", "int", "第一个数"),
            ToolParam("b", "int", "第二个数"),
        ]

        def __call__(self, **kwargs) -> str:
            return str(int(kwargs["a"]) + int(kwargs["b"]))

    t = AddTool()
    assert t(a=1, b=2) == "3"
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/test_tools/test_base.py -v
```

期望：`ImportError` 或 `AttributeError`（Tool/ToolParam 未定义）

- [ ] **Step 3: 重写 `tools/base.py`**

```python
# tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolParam:
    name: str
    type: str        # "str" | "int" | "float" | "bool"
    description: str
    required: bool = True


class Tool(ABC):
    """Base class for all MicroAgent tools.

    Subclasses must define class attributes:
        name: str
        description: str
        parameters: list[ToolParam]

    And implement __call__(**kwargs) -> str.
    """

    name: str
    description: str
    parameters: list

    @abstractmethod
    def __call__(self, **kwargs) -> str:
        """Execute the tool. Must return a string result.
        Catch exceptions internally and return error description as string.
        """
        ...

    def describe(self) -> str:
        """Generate prompt-injection description text."""
        params = ", ".join(
            f"{p.name}: {p.type}" + ("" if p.required else " (可选)")
            for p in self.parameters
        )
        return f"- {self.name}({params}): {self.description}"
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/test_tools/test_base.py -v
```

期望：4 tests PASSED

- [ ] **Step 5: 重写 `tools/web_search.py`**

```python
# tools/web_search.py
try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore

from tools.base import Tool, ToolParam


class WebSearchTool(Tool):
    name = "web_search"
    description = "搜索网络并返回相关结果摘要。提供搜索关键词或完整问题。"
    parameters = [ToolParam("query", "str", "搜索关键词或问题")]

    def __init__(self, tavily_api_key: str = "") -> None:
        self._use_tavily = bool(tavily_api_key)
        self._tavily_api_key = tavily_api_key

    def __call__(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if self._use_tavily:
            return self._search_tavily(query)
        return self._search_duckduckgo(query)

    def _search_tavily(self, query: str) -> str:
        try:
            client = TavilyClient(api_key=self._tavily_api_key)
            response = client.search(query, max_results=5)
            results = response.get("results", [])
            if not results:
                return "未找到相关结果"
            lines = [
                f"{i+1}. {r['title']}\n   {r['url']}\n   {r['content'][:200]}"
                for i, r in enumerate(results)
            ]
            return "\n\n".join(lines)
        except Exception as e:
            return f"错误：Tavily 搜索失败: {e}"

    def _search_duckduckgo(self, query: str) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return "未找到相关结果"
            lines = [
                f"{i+1}. {r['title']}\n   {r['href']}\n   {r['body'][:200]}"
                for i, r in enumerate(results)
            ]
            return "\n\n".join(lines)
        except Exception as e:
            return f"错误：DuckDuckGo 搜索失败: {e}"
```

- [ ] **Step 6: 读取 `tools/file_manager.py` 和 `tools/system_info.py` 当前内容，迁移到新 Tool ABC**

读取这两个文件，把 `MicroTool` 基类改为 `Tool`，`inputs` 字典改为 `parameters` 列表，`forward()` 改为 `__call__()`，移除 `super().__init__()` 调用（新 ABC 不需要）。

- [ ] **Step 7: 重写 `tools/registry.py`**

```python
# tools/registry.py
from typing import List
from core.config import ToolsConfig
from tools.base import Tool


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

- [ ] **Step 8: 删除 `tools/think.py`**

```
del tools/think.py
```

- [ ] **Step 9: 运行全量测试确认无回归**

```
pytest tests/ -v --tb=short
```

- [ ] **Step 10: 提交**

```
git add tools/ tests/test_tools/
git commit -m "feat(tools): remove smolagents dependency, implement Tool ABC with ToolParam"
```

---

## Task 2: 核心数据类型 + Gemma 解析器

**Files:**
- Create: `core/loop/__init__.py`
- Create: `core/loop/types.py`
- Create: `core/loop/parser.py`
- Create: `tests/test_loop/__init__.py`
- Create: `tests/test_loop/test_types.py`
- Create: `tests/test_loop/test_parser.py`

- [ ] **Step 1: 写 types 失败测试**

新建 `tests/test_loop/test_types.py`：

```python
# tests/test_loop/test_types.py
from core.loop.types import Step, Observation, SynthContext


def test_step_creation():
    s = Step(tool="web_search", args={"query": "中东局势"}, reason="搜索最新信息")
    assert s.tool == "web_search"
    assert s.args == {"query": "中东局势"}
    assert s.reason == "搜索最新信息"


def test_observation_success():
    s = Step(tool="web_search", args={"query": "test"}, reason="test")
    obs = Observation(step=s, result="搜索结果", ok=True, error=None)
    assert obs.ok is True
    assert obs.error is None


def test_observation_failure():
    s = Step(tool="web_search", args={"query": "test"}, reason="test")
    obs = Observation(step=s, result="", ok=False, error="网络超时")
    assert obs.ok is False
    assert obs.error == "网络超时"


def test_synth_context():
    s = Step(tool="web_search", args={}, reason="")
    obs = Observation(step=s, result="r", ok=True, error=None)
    ctx = SynthContext(task="问题", observations=[obs], round=1)
    assert ctx.round == 1
    assert len(ctx.observations) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/test_loop/test_types.py -v
```

- [ ] **Step 3: 创建 `core/loop/__init__.py`（空文件）和 `tests/test_loop/__init__.py`（空文件）**

- [ ] **Step 4: 创建 `core/loop/types.py`**

```python
# core/loop/types.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Step:
    tool: str
    args: dict
    reason: str


@dataclass
class Observation:
    step: Step
    result: str
    ok: bool
    error: str | None


@dataclass
class SynthContext:
    task: str
    observations: list[Observation]
    round: int = 0
```

- [ ] **Step 5: 运行 types 测试，确认通过**

```
pytest tests/test_loop/test_types.py -v
```

- [ ] **Step 6: 写 parser 失败测试**

新建 `tests/test_loop/test_parser.py`：

```python
# tests/test_loop/test_parser.py
from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks


def test_parse_native_simple():
    content = '<|tool_call>call:web_search{query:<|"|>中东局势<|"|>}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "web_search"
    assert result["args"] == {"query": "中东局势"}


def test_parse_native_multiple_args():
    content = '<|tool_call>call:read_file{path:<|"|>/tmp/a.txt<|"|>, encoding:<|"|>utf-8<|"|>}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "read_file"
    assert result["args"]["path"] == "/tmp/a.txt"
    assert result["args"]["encoding"] == "utf-8"


def test_parse_no_match():
    result = parse_gemma_tool_call("这是普通文字，没有工具调用")
    assert result is None


def test_parse_plan_with_json_value():
    steps_json = '[{"tool": "web_search", "args": {"query": "test"}, "reason": "搜索"}]'
    content = f'<|tool_call>call:plan{{steps:<|"|>{steps_json}<|"|>}}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "plan"
    assert result["args"]["steps"] == steps_json


def test_strip_complete_thought():
    content = "<|channel>thought\n我需要搜索一下\n<channel|>\n实际输出内容"
    text, thoughts = strip_thought_blocks(content)
    assert "我需要搜索一下" in thoughts[0]
    assert text == "实际输出内容"


def test_strip_truncated_thought():
    content = "<|channel>thought\n思考中，但被截断了"
    text, thoughts = strip_thought_blocks(content)
    assert text == ""
    assert len(thoughts) == 1


def test_strip_no_thought():
    content = "普通内容，没有 thought 块"
    text, thoughts = strip_thought_blocks(content)
    assert text == content
    assert thoughts == []
```

- [ ] **Step 7: 运行测试，确认失败**

```
pytest tests/test_loop/test_parser.py -v
```

- [ ] **Step 8: 创建 `core/loop/parser.py`**

```python
# core/loop/parser.py
"""Gemma native tool call parser.

Handles two formats:
  1. <|tool_call>call:NAME{key:<|"|>value<|"|>, ...}<tool_call|>
  2. Thought blocks: <|channel>thought...<channel|>  (complete or truncated)
"""
from __future__ import annotations
import re
from typing import Optional

_TOOL_CALL_RE = re.compile(
    r'<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>', re.DOTALL
)
_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)
_THOUGHT_RE = re.compile(r'<\|channel\>thought(.*?)<channel\|>', re.DOTALL)
_THOUGHT_OPEN_RE = re.compile(r'<\|channel\>thought(.*)', re.DOTALL)


def parse_gemma_tool_call(content: str) -> Optional[dict]:
    """Parse the first Gemma native tool call in content.

    Returns {"name": str, "args": dict} or None if not found.
    """
    m = _TOOL_CALL_RE.search(content)
    if not m:
        return None
    name = m.group(1)
    args_raw = m.group(2)
    args = {kv.group(1): kv.group(2) for kv in _KV_RE.finditer(args_raw)}
    return {"name": name, "args": args}


def parse_all_gemma_tool_calls(content: str) -> list[dict]:
    """Parse all Gemma native tool calls in content.

    Returns list of {"name": str, "args": dict}.
    """
    results = []
    for m in _TOOL_CALL_RE.finditer(content):
        name = m.group(1)
        args_raw = m.group(2)
        args = {kv.group(1): kv.group(2) for kv in _KV_RE.finditer(args_raw)}
        results.append({"name": name, "args": args})
    return results


def strip_thought_blocks(content: str) -> tuple[str, list[str]]:
    """Strip Gemma thought/reasoning channel blocks from content.

    Returns (stripped_content, list_of_thought_texts).
    Handles both complete blocks (<|channel>thought...<channel|>)
    and truncated blocks (opened but never closed).
    """
    thoughts: list[str] = []

    # Complete blocks
    complete = list(_THOUGHT_RE.finditer(content))
    if complete:
        for m in complete:
            thoughts.append(m.group(1).strip())
        return _THOUGHT_RE.sub("", content).strip(), thoughts

    # Truncated block
    open_m = _THOUGHT_OPEN_RE.search(content)
    if open_m:
        thoughts.append(open_m.group(1).strip())
        return _THOUGHT_OPEN_RE.sub("", content).strip(), thoughts

    return content, []
```

- [ ] **Step 9: 运行 parser 测试，确认通过**

```
pytest tests/test_loop/test_parser.py -v
```

- [ ] **Step 10: 提交**

```
git add core/loop/ tests/test_loop/
git commit -m "feat(loop): add core data types and Gemma native parser"
```

---

## Task 3: Prompt 模板

**Files:**
- Create: `core/loop/prompt.py`

- [ ] **Step 1: 创建 `core/loop/prompt.py`**

```python
# core/loop/prompt.py
"""Prompt templates for the Plan-then-Execute agent loop.

All prompts use Gemma native tool call format exclusively.
Tool descriptions are dynamically injected — no hardcoded examples.
"""
from __future__ import annotations

PLANNER_SYSTEM = """\
你是一个任务规划助手。分析用户任务，选择完成任务必要的工具，输出一个有序的执行计划。

可用工具：
{tools_description}

输出格式（严格使用以下 Gemma tool call 格式，不得使用其他格式）：
<|tool_call>call:plan{{steps:<|"|>[{{"tool": "工具名", "args": {{...}}, "reason": "原因"}}]<|"|>}}<tool_call|>

规则：
- 只选择完成任务真正必要的工具，不要冗余步骤
- 最多 {max_plan_steps} 步
- args 必须完整匹配工具的参数定义
"""

PLANNER_USER = "用户任务：{task}"

SYNTHESIZER_SYSTEM = """\
你是一个回答助手。根据以下工具执行结果，回答用户的问题。

如果现有信息已经足够，直接输出答案文本（不需要任何特殊格式，直接写答案即可）。
如果还需要查询更多信息，使用以下格式调用工具：
<|tool_call>call:工具名{{参数名:<|"|>参数值<|"|>}}<tool_call|>

可追加使用的工具：
{tools_description}
"""

SYNTHESIZER_USER = """\
用户任务：{task}

执行结果：
{observations_text}
"""


def format_observations(observations: list) -> str:
    """Format a list of Observation into readable text for the Synthesizer prompt."""
    lines = []
    for i, obs in enumerate(observations, 1):
        status = "✓" if obs.ok else "✗"
        args_str = ", ".join(f"{k}={v!r}" for k, v in obs.step.args.items())
        lines.append(f"{i}. {status} {obs.step.tool}({args_str})")
        if obs.ok:
            lines.append(f"   结果：{obs.result[:500]}")
        else:
            lines.append(f"   错误：{obs.error}")
    return "\n".join(lines)


def format_tools(tools: list) -> str:
    """Generate tool description block for prompt injection."""
    return "\n".join(t.describe() for t in tools)
```

- [ ] **Step 2: 写 prompt 测试**

新建 `tests/test_loop/test_prompt.py`：

```python
# tests/test_loop/test_prompt.py
from core.loop.prompt import format_observations, format_tools
from core.loop.types import Step, Observation
from tools.base import Tool, ToolParam


class DummyTool(Tool):
    name = "dummy"
    description = "测试工具"
    parameters = [ToolParam("x", "str", "输入")]

    def __call__(self, **kwargs) -> str:
        return ""


def test_format_tools():
    t = DummyTool()
    result = format_tools([t])
    assert "dummy(x: str)" in result
    assert "测试工具" in result


def test_format_observations_success():
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    obs = Observation(step=s, result="搜索结果内容", ok=True, error=None)
    text = format_observations([obs])
    assert "✓" in text
    assert "web_search" in text
    assert "搜索结果内容" in text


def test_format_observations_failure():
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    obs = Observation(step=s, result="", ok=False, error="超时")
    text = format_observations([obs])
    assert "✗" in text
    assert "超时" in text
```

- [ ] **Step 3: 运行测试，确认通过**

```
pytest tests/test_loop/test_prompt.py -v
```

- [ ] **Step 4: 提交**

```
git add core/loop/prompt.py tests/test_loop/test_prompt.py
git commit -m "feat(loop): add prompt templates and formatting helpers"
```

---

## Task 4: Planner

**Files:**
- Create: `core/loop/planner.py`
- Create: `tests/test_loop/test_planner.py`

- [ ] **Step 1: 写 Planner 失败测试**

新建 `tests/test_loop/test_planner.py`：

```python
# tests/test_loop/test_planner.py
import json
import pytest
from unittest.mock import MagicMock
from core.loop.planner import Planner
from core.loop.types import Step
from tools.base import Tool, ToolParam


class MockSearchTool(Tool):
    name = "web_search"
    description = "搜索网络"
    parameters = [ToolParam("query", "str", "搜索词")]
    def __call__(self, **kwargs) -> str: return ""


def make_model(raw_output: str):
    """Create a mock model that returns raw_output when called."""
    model = MagicMock()
    model.generate = MagicMock(return_value=raw_output)
    return model


def gemma_plan(steps: list) -> str:
    steps_json = json.dumps(steps, ensure_ascii=False)
    return f'<|tool_call>call:plan{{steps:<|"|>{steps_json}<|"|>}}<tool_call|>'


def test_planner_returns_steps():
    raw = gemma_plan([
        {"tool": "web_search", "args": {"query": "中东"}, "reason": "搜索"},
    ])
    model = make_model(raw)
    tools = [MockSearchTool()]
    planner = Planner(model=model, tools=tools, max_plan_steps=10)
    plan = planner.plan("预测中东局势")
    assert len(plan) == 1
    assert isinstance(plan[0], Step)
    assert plan[0].tool == "web_search"
    assert plan[0].args == {"query": "中东"}


def test_planner_multiple_steps():
    raw = gemma_plan([
        {"tool": "web_search", "args": {"query": "A"}, "reason": "第一步"},
        {"tool": "web_search", "args": {"query": "B"}, "reason": "第二步"},
    ])
    model = make_model(raw)
    planner = Planner(model=make_model(raw), tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert len(plan) == 2


def test_planner_retry_on_parse_failure():
    good_raw = gemma_plan([{"tool": "web_search", "args": {"query": "x"}, "reason": "r"}])
    call_count = 0

    def side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "无效输出"
        return good_raw

    model = MagicMock()
    model.generate = MagicMock(side_effect=side_effect)
    planner = Planner(model=model, tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert call_count == 2
    assert len(plan) == 1


def test_planner_raises_after_two_failures():
    model = make_model("无效输出，无法解析")
    planner = Planner(model=model, tools=[MockSearchTool()], max_plan_steps=10)
    with pytest.raises(RuntimeError, match="无法生成执行计划"):
        planner.plan("任务")
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/test_loop/test_planner.py -v
```

- [ ] **Step 3: 创建 `core/loop/planner.py`**

```python
# core/loop/planner.py
from __future__ import annotations
import json
import logging
from typing import Any

from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks
from core.loop.prompt import PLANNER_SYSTEM, PLANNER_USER, format_tools
from core.loop.types import Step

_log = logging.getLogger(__name__)


class Planner:
    """Calls the model once to produce a structured execution plan."""

    def __init__(self, model: Any, tools: list, max_plan_steps: int = 10) -> None:
        self._model = model
        self._tools = tools
        self._max_plan_steps = max_plan_steps

    def plan(self, task: str) -> list[Step]:
        """Generate an execution plan for the given task.

        Returns list of Step. Retries once on parse failure.
        Raises RuntimeError if both attempts fail.
        """
        for attempt in range(2):
            raw = self._call_model(task)
            steps = self._parse(raw)
            if steps is not None:
                return steps
            _log.warning("Planner parse failure (attempt %d/2). Raw: %r", attempt + 1, raw[:200])

        raise RuntimeError("无法生成执行计划：模型连续两次未输出合法计划格式")

    def _call_model(self, task: str) -> str:
        tools_desc = format_tools(self._tools)
        system = PLANNER_SYSTEM.format(
            tools_description=tools_desc,
            max_plan_steps=self._max_plan_steps,
        )
        user = PLANNER_USER.format(task=task)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._model.generate(messages)
        content, _ = strip_thought_blocks(raw)
        return content

    def _parse(self, content: str) -> list[Step] | None:
        result = parse_gemma_tool_call(content)
        if result is None or result["name"] != "plan":
            return None
        steps_raw = result["args"].get("steps", "")
        try:
            steps_data = json.loads(steps_raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(steps_data, list) or not steps_data:
            return None
        steps = []
        for item in steps_data:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool", "")
            args = item.get("args", {})
            reason = item.get("reason", "")
            if tool and isinstance(args, dict):
                steps.append(Step(tool=tool, args=args, reason=reason))
        return steps if steps else None
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/test_loop/test_planner.py -v
```

期望：4 tests PASSED

- [ ] **Step 5: 提交**

```
git add core/loop/planner.py tests/test_loop/test_planner.py
git commit -m "feat(loop): add Planner with retry on parse failure"
```

---

## Task 5: Executor

**Files:**
- Create: `core/loop/executor.py`
- Create: `tests/test_loop/test_executor.py`

- [ ] **Step 1: 写 Executor 失败测试**

新建 `tests/test_loop/test_executor.py`：

```python
# tests/test_loop/test_executor.py
import pytest
from core.loop.executor import Executor
from core.loop.types import Step, Observation
from tools.base import Tool, ToolParam


class OkTool(Tool):
    name = "ok_tool"
    description = "成功工具"
    parameters = [ToolParam("x", "str", "输入")]
    def __call__(self, **kwargs) -> str:
        return f"结果: {kwargs.get('x', '')}"


class FailTool(Tool):
    name = "fail_tool"
    description = "总是失败"
    parameters = []
    def __call__(self, **kwargs) -> str:
        raise ValueError("工具执行失败")


def test_executor_success():
    executor = Executor(tools=[OkTool()])
    step = Step(tool="ok_tool", args={"x": "hello"}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is True
    assert obs.result == "结果: hello"
    assert obs.error is None


def test_executor_tool_raises():
    executor = Executor(tools=[FailTool()])
    step = Step(tool="fail_tool", args={}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is False
    assert "工具执行失败" in obs.error


def test_executor_unknown_tool():
    executor = Executor(tools=[OkTool()])
    step = Step(tool="nonexistent", args={}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is False
    assert "nonexistent" in obs.error


def test_executor_run_plan():
    executor = Executor(tools=[OkTool()])
    plan = [
        Step(tool="ok_tool", args={"x": "a"}, reason=""),
        Step(tool="ok_tool", args={"x": "b"}, reason=""),
    ]
    observations = executor.run_plan(plan)
    assert len(observations) == 2
    assert all(o.ok for o in observations)


def test_executor_run_plan_continues_on_failure():
    executor = Executor(tools=[OkTool(), FailTool()])
    plan = [
        Step(tool="fail_tool", args={}, reason=""),
        Step(tool="ok_tool", args={"x": "继续"}, reason=""),
    ]
    observations = executor.run_plan(plan)
    assert len(observations) == 2
    assert observations[0].ok is False
    assert observations[1].ok is True
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/test_loop/test_executor.py -v
```

- [ ] **Step 3: 创建 `core/loop/executor.py`**

```python
# core/loop/executor.py
from __future__ import annotations
import logging
from typing import Any

from core.loop.types import Step, Observation

_log = logging.getLogger(__name__)


class Executor:
    """Executes tool calls from a plan, collecting Observations.

    Tool exceptions are caught and recorded as failed Observations —
    execution continues to the next step.
    """

    def __init__(self, tools: list) -> None:
        self._tools: dict[str, Any] = {t.name: t for t in tools}

    def execute(self, step: Step) -> Observation:
        """Execute a single step. Never raises — errors become Observations."""
        tool = self._tools.get(step.tool)
        if tool is None:
            err = f"未知工具: {step.tool!r}。可用工具: {list(self._tools.keys())}"
            _log.warning(err)
            return Observation(step=step, result="", ok=False, error=err)
        try:
            result = tool(**step.args)
            _log.info("Tool %r OK. Result length: %d", step.tool, len(result))
            return Observation(step=step, result=str(result), ok=True, error=None)
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            _log.warning("Tool %r raised: %s", step.tool, err)
            return Observation(step=step, result="", ok=False, error=err)

    def run_plan(self, plan: list[Step]) -> list[Observation]:
        """Execute all steps in order. Continues even if a step fails."""
        observations = []
        for step in plan:
            obs = self.execute(step)
            observations.append(obs)
        return observations
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/test_loop/test_executor.py -v
```

期望：5 tests PASSED

- [ ] **Step 5: 提交**

```
git add core/loop/executor.py tests/test_loop/test_executor.py
git commit -m "feat(loop): add Executor with error isolation"
```

---

## Task 6: Synthesizer

**Files:**
- Create: `core/loop/synthesizer.py`
- Create: `tests/test_loop/test_synthesizer.py`

- [ ] **Step 1: 写 Synthesizer 失败测试**

新建 `tests/test_loop/test_synthesizer.py`：

```python
# tests/test_loop/test_synthesizer.py
import pytest
from unittest.mock import MagicMock
from core.loop.synthesizer import Synthesizer
from core.loop.types import Step, Observation, SynthContext
from tools.base import Tool, ToolParam


class MockSearchTool(Tool):
    name = "web_search"
    description = "搜索"
    parameters = [ToolParam("query", "str", "词")]
    def __call__(self, **kwargs) -> str:
        return f"搜索结果: {kwargs.get('query')}"


def make_obs(result="搜索结果"):
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    return Observation(step=s, result=result, ok=True, error=None)


def test_synthesizer_plain_text_is_final_answer():
    model = MagicMock()
    model.generate = MagicMock(return_value="这是最终答案，不含工具调用")
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == "这是最终答案，不含工具调用"
    assert model.generate.call_count == 1


def test_synthesizer_tool_call_triggers_extra_round():
    tool_call = '<|tool_call>call:web_search{query:<|"|>追加搜索<|"|>}<tool_call|>'
    call_count = 0

    def side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_call
        return "最终综合答案"

    model = MagicMock()
    model.generate = MagicMock(side_effect=side_effect)
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert call_count == 2
    assert answer == "最终综合答案"


def test_synthesizer_max_rounds_forces_answer():
    model = MagicMock()
    tool_call = '<|tool_call>call:web_search{query:<|"|>一直搜索<|"|>}<tool_call|>'
    model.generate = MagicMock(return_value=tool_call)
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=3)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    # After max_rounds, falls back to forced synthesis
    assert answer is not None
    assert isinstance(answer, str)


def test_synthesizer_strips_thought_before_checking():
    thought = "<|channel>thought\n我需要思考一下\n<channel|>\n"
    answer_text = "这是答案"
    model = MagicMock()
    model.generate = MagicMock(return_value=thought + answer_text)
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == answer_text
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/test_loop/test_synthesizer.py -v
```

- [ ] **Step 3: 创建 `core/loop/synthesizer.py`**

```python
# core/loop/synthesizer.py
from __future__ import annotations
import logging
from typing import Any

from core.loop.executor import Executor
from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks
from core.loop.prompt import (
    SYNTHESIZER_SYSTEM, SYNTHESIZER_USER,
    format_observations, format_tools,
)
from core.loop.types import Step, Observation, SynthContext

_log = logging.getLogger(__name__)


class Synthesizer:
    """Calls the model to synthesize a final answer from observations.

    If the model outputs a tool call, it executes the tool, appends the
    new observation, and calls the model again — up to max_rounds times.
    If the model outputs plain text, it is returned directly as the answer.
    """

    def __init__(self, model: Any, tools: list, max_rounds: int = 5) -> None:
        self._model = model
        self._tools = tools
        self._executor = Executor(tools)
        self._max_rounds = max_rounds

    def synthesize(self, ctx: SynthContext) -> str:
        observations = list(ctx.observations)

        for round_num in range(self._max_rounds):
            raw = self._call_model(ctx.task, observations, round_num)
            content, thoughts = strip_thought_blocks(raw)
            if thoughts:
                _log.debug("Synthesizer thought (stripped): %s", thoughts[0][:200])

            tool_call = parse_gemma_tool_call(content)
            if tool_call is None:
                # Plain text → final answer
                answer = content.strip()
                _log.info("Synthesizer produced final answer (%d chars)", len(answer))
                return answer

            # Tool call → execute and loop
            name = tool_call["name"]
            args = tool_call["args"]
            _log.info("Synthesizer round %d: tool call %r args=%r", round_num + 1, name, args)
            step = Step(tool=name, args=args, reason=f"synthesizer round {round_num + 1}")
            obs = self._executor.execute(step)
            observations.append(obs)

        # Exceeded max_rounds — force a final answer with current observations
        _log.warning("Synthesizer exceeded max_rounds=%d, forcing final answer", self._max_rounds)
        return self._force_answer(ctx.task, observations)

    def _call_model(self, task: str, observations: list[Observation], round_num: int) -> str:
        tools_desc = format_tools(self._tools)
        obs_text = format_observations(observations)
        system = SYNTHESIZER_SYSTEM.format(tools_description=tools_desc)
        user = SYNTHESIZER_USER.format(task=task, observations_text=obs_text)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._model.generate(messages)

    def _force_answer(self, task: str, observations: list[Observation]) -> str:
        """Last resort: ask model to answer with what we have, no tool calls allowed."""
        obs_text = format_observations(observations)
        system = "你是回答助手。根据以下信息直接回答问题，不要调用任何工具，信息可能不完整。"
        user = f"问题：{task}\n\n已收集信息：\n{obs_text}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._model.generate(messages)
        content, _ = strip_thought_blocks(raw)
        return content.strip() or "（无法生成答案，信息不足）"
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/test_loop/test_synthesizer.py -v
```

期望：4 tests PASSED

- [ ] **Step 5: 提交**

```
git add core/loop/synthesizer.py tests/test_loop/test_synthesizer.py
git commit -m "feat(loop): add Synthesizer with tool-call loop and max_rounds guard"
```

---

## Task 7: 重写 core/model.py

**Files:**
- Modify: `core/model.py`

- [ ] **Step 1: 重写 `core/model.py`**

移除所有 smolagents 依赖和多策略解析器（Strategy 1.5/2/2.5），保留 `LlamaCppBackend` 但改变接口：提供 `generate(messages: list[dict]) -> str`。

```python
# core/model.py
import logging
from abc import ABC, abstractmethod
from typing import Any

from core.config import ModelConfig

_log = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore


class ModelBackend(ABC):
    """Abstract inference backend."""

    @abstractmethod
    def load(self) -> None:
        """Load model into memory."""

    @abstractmethod
    def generate(self, messages: list[dict]) -> str:
        """Call the model with a list of chat messages, return raw text output."""

    @abstractmethod
    def get_memory_usage_gb(self) -> float:
        """Return current process RSS in GB."""

    @abstractmethod
    def get_gpu_info(self) -> str:
        """Return short GPU/CPU backend label."""


class LlamaCppBackend(ModelBackend):
    def __init__(self, config: ModelConfig) -> None:
        self._config = config
        self._llm = None

    def load(self) -> None:
        self._llm = Llama(
            model_path=self._config.path,
            n_gpu_layers=self._config.n_gpu_layers,
            n_threads=self._config.n_threads,
            n_ctx=self._config.n_ctx,
            flash_attn=True,
            verbose=False,
        )

    def generate(self, messages: list[dict]) -> str:
        """Call the model. Returns raw text content (no parsing)."""
        if self._llm is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=self._config.max_tokens,
        )
        content = response["choices"][0]["message"].get("content") or ""
        _log.info("LLM raw output: %r", content[:600] if content else "<empty>")
        return content

    def get_memory_usage_gb(self) -> float:
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)

    def get_gpu_info(self) -> str:
        if self._llm is None:
            return "未加载"
        try:
            from llama_cpp import llama_cpp as _lib
            try:
                full_info = _lib.llama_print_system_info().decode("utf-8", errors="replace")
            except Exception:
                full_info = ""
            if full_info:
                _log.info("llama.cpp system info: %s", full_info.strip())
            if not _lib.llama_supports_gpu_offload():
                return "CPU（llama-cpp-python 未编译 GPU 支持）"
            if self._config.n_gpu_layers == 0:
                return "CPU（n_gpu_layers=0）"
            info_upper = full_info.upper()
            if "CUDA" in info_upper:
                backend = "CUDA"
            elif "VULKAN" in info_upper:
                backend = "Vulkan"
            elif "METAL" in info_upper:
                backend = "Metal"
            elif "ROCM" in info_upper:
                backend = "ROCm"
            else:
                backend = "GPU"
            layers = "全部层" if self._config.n_gpu_layers == -1 else f"{self._config.n_gpu_layers} 层"
            return f"{backend}（{layers}）"
        except Exception:
            layers = self._config.n_gpu_layers
            return f"GPU（n_gpu_layers={layers}，无法确认设备）"
```

- [ ] **Step 2: 运行全量测试**

```
pytest tests/ -v --tb=short
```

期望：所有之前通过的测试仍然通过（model.py 相关测试可能需要更新）

- [ ] **Step 3: 提交**

```
git add core/model.py
git commit -m "refactor(model): remove smolagents wrapper, LlamaCppBackend.generate() returns raw str"
```

---

## Task 8: 重写 core/agent.py + 更新 config

**Files:**
- Modify: `core/agent.py`
- Modify: `core/config.py`

- [ ] **Step 1: 更新 `core/config.py` 的 AgentConfig**

把 `AgentConfig` 的 `mode` 字段改为 `plan_execute`，新增 `max_exec_rounds` 和 `max_plan_steps`：

```python
class AgentConfig(BaseModel):
    mode: Literal["plan_execute"] = "plan_execute"
    verbose: bool = False
    show_thinking: bool = True
    max_exec_rounds: int = 5
    max_plan_steps: int = 10
```

同时更新 `config.yaml`，新增字段：

```yaml
agent:
  mode: plan_execute
  verbose: false
  show_thinking: true
  max_exec_rounds: 5
  max_plan_steps: 10
```

- [ ] **Step 2: 重写 `core/agent.py`**

```python
# core/agent.py
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any

from core.config import AgentConfig
from core.loop.planner import Planner
from core.loop.executor import Executor
from core.loop.synthesizer import Synthesizer
from core.loop.types import SynthContext

_log = logging.getLogger(__name__)


class AgentRunner(ABC):
    """Abstract runner — implementations define the agent loop strategy."""

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Execute a task and return the final answer."""


class PlanExecuteRunner(AgentRunner):
    """Plan-then-Execute agent loop.

    1. Planner calls the model once to produce a structured plan.
    2. Executor runs all plan steps, collecting observations.
    3. Synthesizer calls the model to produce a final answer,
       optionally requesting more tool calls (up to max_exec_rounds).
    """

    def __init__(
        self,
        model: Any,
        tools: list,
        config: AgentConfig,
        show_thinking: bool = True,
    ) -> None:
        self._model = model
        self._tools = tools
        self._config = config
        self._show_thinking = show_thinking
        self._planner = Planner(
            model=model,
            tools=tools,
            max_plan_steps=config.max_plan_steps,
        )
        self._executor = Executor(tools=tools)
        self._synthesizer = Synthesizer(
            model=model,
            tools=tools,
            max_rounds=config.max_exec_rounds,
        )

    def run(self, prompt: str) -> str:
        _log.info("PlanExecuteRunner.run: task=%r", prompt[:100])

        # Phase 1: Plan
        try:
            plan = self._planner.plan(prompt)
        except RuntimeError as e:
            _log.error("Planner failed: %s", e)
            return f"规划失败：{e}"

        _log.info("Plan: %d steps", len(plan))
        if self._config.verbose:
            for i, step in enumerate(plan, 1):
                _log.info("  Step %d: %s(%s) — %s", i, step.tool, step.args, step.reason)

        # Phase 2: Execute
        observations = self._executor.run_plan(plan)

        # Phase 3: Synthesize
        ctx = SynthContext(task=prompt, observations=observations, round=0)
        answer = self._synthesizer.synthesize(ctx)
        return answer


def create_agent_runner(
    config: AgentConfig,
    model: Any,
    tools: list,
) -> AgentRunner:
    return PlanExecuteRunner(
        model=model,
        tools=tools,
        config=config,
        show_thinking=config.show_thinking,
    )
```

- [ ] **Step 3: 运行全量测试**

```
pytest tests/ -v --tb=short
```

- [ ] **Step 4: 提交**

```
git add core/agent.py core/config.py config.yaml
git commit -m "feat(agent): implement PlanExecuteRunner, remove smolagents ToolCallingAgent"
```

---

## Task 9: 更新 main.py + 移除 smolagents 依赖

**Files:**
- Modify: `main.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 读取 `main.py` 当前内容**

检查 `main.py` 中所有 smolagents 相关调用（`to_smolagents_model`、`LogLevel` 等）。

- [ ] **Step 2: 更新 `main.py`**

把 `backend.to_smolagents_model()` 调用改为直接把 `backend` 作为 model 传入 `create_agent_runner`：

```python
# 旧:
smolagents_model = backend.to_smolagents_model(show_thinking=config.agent.show_thinking)
agent = create_agent_runner(config.agent, smolagents_model, tools)

# 新:
agent = create_agent_runner(config.agent, backend, tools)
```

移除所有 smolagents 相关 import。

- [ ] **Step 3: 从 `requirements.txt` 移除 smolagents**

删除 `smolagents` 那一行。

- [ ] **Step 4: 运行完整启动测试（dry run，不调模型）**

```
python -c "from main import main; print('import OK')"
```

- [ ] **Step 5: 运行全量测试**

```
pytest tests/ -v --tb=short
```

- [ ] **Step 6: 提交**

```
git add main.py requirements.txt
git commit -m "chore: remove smolagents from main.py and requirements.txt"
```

---

## Task 10: show_thinking 集成到 PlanExecuteRunner

**Files:**
- Modify: `core/loop/planner.py`
- Modify: `core/loop/synthesizer.py`

- [ ] **Step 1: 在 Planner 和 Synthesizer 的 `_call_model` 中展示 thought**

在 `planner.py` 的 `_call_model` 中，`strip_thought_blocks` 后如果有 thoughts 且 `show_thinking=True`，打印到 stdout：

```python
# planner.py _call_model 末尾
content, thoughts = strip_thought_blocks(raw)
if show_thinking and thoughts:
    import sys
    sys.stdout.write(f"\033[2m💭 {thoughts[0]}\033[0m\n")
    sys.stdout.flush()
return content
```

但 `Planner` 目前不持有 `show_thinking`。需要在构造时接收并存储。

在 `core/loop/planner.py` 的 `__init__` 加 `show_thinking: bool = True` 参数，并在 `_call_model` 里使用。

在 `core/loop/synthesizer.py` 同样处理。

在 `core/agent.py` 的 `PlanExecuteRunner.__init__` 里把 `show_thinking` 传给 `Planner` 和 `Synthesizer`。

- [ ] **Step 2: 运行全量测试**

```
pytest tests/ -v --tb=short
```

- [ ] **Step 3: 提交**

```
git add core/loop/planner.py core/loop/synthesizer.py core/agent.py
git commit -m "feat(loop): route show_thinking to Planner and Synthesizer thought display"
```

---

## Task 11: 端到端冒烟测试 + 最终清理

- [ ] **Step 1: 运行全量测试**

```
pytest tests/ -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 2: 删除 `tools/think.py`**

```
git rm tools/think.py
```

- [ ] **Step 3: 检查是否还有 smolagents 残留引用**

```
grep -r "smolagents" . --include="*.py" --exclude-dir=".venv"
```

期望：无任何输出（所有引用已清除）

- [ ] **Step 4: 启动应用验证（手动）**

```
python run.py
```

输入"你好"，确认收到回复且无报错。

- [ ] **Step 5: 最终提交**

```
git add -A
git commit -m "chore: final cleanup, remove think.py, verify no smolagents references"
```

---

## 自审

**Spec 覆盖检查：**
- ✅ Plan-then-Execute 架构（Task 4-6）
- ✅ Execute-Synthesize Loop with max_exec_rounds（Task 6）
- ✅ Synthesizer 纯文本=最终答案，无需 final_answer 工具（Task 6）
- ✅ Tool ABC 移除 smolagents（Task 1）
- ✅ 仅 Gemma native 格式（Task 2 parser）
- ✅ prompt 模板集中管理（Task 3）
- ✅ config.yaml 新增字段（Task 8）
- ✅ 完全移除 smolagents（Task 9）
- ✅ show_thinking 路由（Task 10）

**类型一致性：**
- `Planner.plan()` → `list[Step]` ✅
- `Executor.run_plan()` → `list[Observation]` ✅
- `Synthesizer.synthesize(SynthContext)` → `str` ✅
- `ModelBackend.generate(list[dict])` → `str` ✅
- `AgentRunner.run(str)` → `str` ✅
