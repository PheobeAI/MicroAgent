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

【输出格式】必须严格按照以下格式，不得有任何偏差：
<|tool_call>call:plan{{steps:<|"|>[STEPS_JSON]<|"|>}}<tool_call|>

其中 STEPS_JSON 是标准 JSON 数组，每个元素格式如下：
{{"tool": "工具名称", "args": {{"参数名": "参数值"}}, "reason": "选择该工具的原因"}}

【完整示例】（假设任务是"搜索天气"）：
<|tool_call>call:plan{{steps:<|"|>[{{"tool": "web_search", "args": {{"query": "今日天气预报"}}, "reason": "需要搜索最新天气信息"}}]<|"|>}}<tool_call|>

【强制规则】：
1. steps 的值必须用 <|"|> 和 <|"|> 包裹，内部是合法的 JSON 数组
2. JSON 中所有 key 和字符串 value 必须使用双引号，不得使用单引号或不加引号
3. args 必须是 JSON 对象格式，不得写成普通字符串
4. 只选择完成任务真正必要的步骤，最多 {max_plan_steps} 步
5. 除了上述 tool call 格式，不得输出任何其他内容
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