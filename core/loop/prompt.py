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
