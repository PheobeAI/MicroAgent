# Agent Loop 设计文档

**日期**：2026-04-13  
**状态**：已批准，待实现  
**背景**：移除 smolagents 依赖，重写 Agent Loop，彻底解决模型输出格式污染问题

---

## 1. 问题背景

smolagents 的 `ToolCallingAgent` 存在根本性架构问题：

- `ActionStep.to_messages()` 用 `str([tc.dict()...])` 把历史 tool call 注入 prompt，产生 Python 单引号格式
- 模型在 context 里看到什么格式就输出什么格式（Python dict、smolagents JSON、Gemma native 混乱交替）
- `stop_sequences=["Observation:"]` 被传给 llama-cpp，导致 prompt 末尾含 `Observation:` 时模型立即输出 `<eos>`
- 解析层在 smolagents 内部，我们无法干预，只能在外层打补丁（已堆积 5 种解析策略）

**决策**：完全移除 smolagents，包括其 Tool 基类，自己实现 Agent Loop。

---

## 2. 架构设计

### 2.1 整体流程

```
用户输入
   │
   ▼
┌──────────┐
│ Planner  │  调模型一次，输出结构化执行计划（step list）
└────┬─────┘
     │ Plan = list[Step]
     ▼
┌──────────────────────────────────────┐
│      Execute-Synthesize Loop         │  最多 max_exec_rounds 轮（可配置）
│                                      │
│  ┌──────────┐      ┌──────────────┐  │
│  │ Executor │ ───→ │ Synthesizer  │  │
│  └──────────┘      └──────┬───────┘  │
│        ↑                  │          │
│        │          工具调用？           │
│        │    yes ──┘    no │          │
│        └──────────        ↓          │
│                      最终答案（文本）  │
└──────────────────────────────────────┘
```

- **Planner**：调模型一次，产出执行计划。失败则重试一次。
- **Executor**：纯 Python，按计划逐步执行工具，收集 Observation。
- **Synthesizer**：调模型，根据 Observation 生成答案。若模型输出工具调用则追加执行，若输出纯文本则直接作为最终答案。
- **Loop 上限**：`max_exec_rounds`（默认 5，可在 `config.yaml` 配置）

### 2.2 文件结构

```
core/
  agent.py           # AgentRunner ABC + PlanExecuteRunner（重写）
  loop/
    __init__.py
    planner.py       # Planner：调模型，解析计划
    executor.py      # Executor：执行单个工具调用
    synthesizer.py   # Synthesizer：汇总，支持追加工具调用
    prompt.py        # 所有 prompt 模板（集中管理）
    parser.py        # Gemma native 格式解析器（从 model.py 迁移）
tools/
  base.py            # Tool ABC（替换 smolagents.Tool）
  web_search.py      # 重写，继承自 tools.base.Tool
  （其他工具）
```

---

## 3. 核心数据结构

```python
# 执行计划中的单个步骤
@dataclass
class Step:
    tool: str           # 工具名
    args: dict          # 工具参数
    reason: str         # 为什么要执行这步（用于 prompt 构造）

# 工具执行结果
@dataclass
class Observation:
    step: Step
    result: str         # 工具返回的字符串
    ok: bool            # 是否成功
    error: str | None   # 失败时的错误消息

# Synthesizer 上下文
@dataclass
class SynthContext:
    task: str
    observations: list[Observation]
    round: int
```

---

## 4. Prompt 设计

### 4.1 Planner Prompt

```
<system>
你是一个任务规划助手。分析用户任务，选择必要的工具，输出一个有序的执行计划。

可用工具（根据任务动态选择）：
{tools_description}

输出格式（严格使用 Gemma native tool call 格式）：
<|tool_call>call:plan{steps:<|"|>[{"tool": "工具名", "args": {...}, "reason": "原因"}]<|"|>}<tool_call|>

规则：
- 只选择完成任务必要的工具，不要冗余步骤
- 最多 {max_plan_steps} 步
- 最后一步通常是 synthesize（表示已收集完信息，可以汇总）
</system>

用户任务：{task}
```

### 4.2 Synthesizer Prompt

```
<system>
你是一个回答助手。根据以下执行结果，回答用户的问题。

如果现有信息足够，直接输出答案文本（不需要任何特殊格式）。
如果还需要查询更多信息，使用工具调用格式：
<|tool_call>call:工具名{参数}<tool_call|>

可追加使用的工具：
{tools_description}
</system>

用户任务：{task}

执行结果：
{observations_text}
```

### 4.3 Prompt 模板管理

- 所有模板集中在 `core/loop/prompt.py`
- 工具描述动态注入（Planner 阶段根据任务类型选择相关工具子集）
- 不在 prompt 里混入任何 Python dict、JSON 示例，只用 Gemma native 格式示例

---

## 5. Tool ABC

```python
# tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolParam:
    name: str
    type: str           # "str" | "int" | "float" | "bool"
    description: str
    required: bool = True

class Tool(ABC):
    name: str                       # 工具名（用于 tool call 解析）
    description: str                # 自然语言描述（注入 prompt）
    parameters: list[ToolParam]     # 参数列表（注入 prompt，生成参数说明）

    @abstractmethod
    def __call__(self, **kwargs) -> str:
        """执行工具，返回字符串结果。异常应捕获后返回错误描述字符串。"""
        ...

    def describe(self) -> str:
        """生成注入 prompt 用的工具描述文本。"""
        params = ", ".join(
            f"{p.name}: {p.type}" + ("" if p.required else " (可选)")
            for p in self.parameters
        )
        return f"- {self.name}({params}): {self.description}"
```

---

## 6. 错误处理

| 场景 | 处理方式 |
|---|---|
| Planner 解析失败 | 重试一次；仍失败则返回"无法规划任务"给用户 |
| 工具执行异常 | `Observation.ok=False`，error 文本追加到 context，继续后续步骤 |
| Synthesizer 超过 `max_exec_rounds` | 以当前 observations 强制生成答案，附加提示"信息可能不完整" |
| Synthesizer 输出纯文本 | 直接作为最终答案（**不需要 `final_answer` 工具调用**） |
| Synthesizer 输出工具调用 | 执行工具，追加 Observation，进入下一轮 |
| 模型输出无法解析 | 记录 WARNING，Synthesizer 重试一次 |

---

## 7. config.yaml 新增字段

```yaml
agent:
  mode: plan_execute          # 固定值，移除 tool_calling / code 模式
  max_exec_rounds: 5          # Execute-Synthesize Loop 最大轮数
  max_plan_steps: 10          # 单次计划最多步骤数
  show_thinking: true         # 是否展示模型 thought channel 内容
  verbose: false              # 是否输出详细 step 信息到控制台
```

---

## 8. 移除内容

- `smolagents` 依赖（从 `requirements.txt` 移除）
- `core/agent.py` 中所有 smolagents 相关代码
- `tools/think.py`（ThinkTool，已不再需要）
- `core/model.py` 中的多策略解析器（Strategy 1.5、2、2.5）——保留 Strategy 1（Gemma native），其余全删

---

## 9. 与现有系统的兼容

- `core/model.py` 的 `LlamaCppBackend` 保留，只是不再需要 `_LlamaCppSmolagentsModel`，改为提供一个简单的 `generate(messages) -> str` 接口
- `memory/` 模块不受影响
- `cli/app.py` 的 `_run_task` 只需要 `AgentRunner.run(prompt) -> str`，接口不变
- `main.py` 的初始化流程基本不变，只是不再调用 `to_smolagents_model()`

---

## 10. 测试策略

- `tests/test_loop/test_planner.py` — Planner 解析 Gemma native 格式计划
- `tests/test_loop/test_executor.py` — Executor 工具执行与错误捕获
- `tests/test_loop/test_synthesizer.py` — Synthesizer 工具调用 vs 纯文本输出判断
- `tests/test_tools/test_base.py` — Tool ABC 和 describe() 方法
- 所有测试使用 mock 模型，不依赖真实推理
