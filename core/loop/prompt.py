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

【输出格式】必须严格输出一个 JSON 对象，不得有任何其他内容：
{{"steps": [STEPS_ARRAY]}}

其中 STEPS_ARRAY 是 JSON 数组，每个元素格式：
{{"tool": "工具名称", "args": {{"参数名": "参数值"}}, "reason": "选择原因"}}

【完整示例】（任务是"搜索天气"）：
{{"steps": [{{"tool": "web_search", "args": {{"query": "今日天气预报"}}, "reason": "需要搜索最新天气信息"}}]}}

【多步示例】（任务是"先查记忆再搜索"）：
{{"steps": [{{"tool": "memory_recall", "args": {{}}, "reason": "查询已知信息"}}, {{"tool": "web_search", "args": {{"query": "搜索词"}}, "reason": "补充最新信息"}}]}}

【强制规则】：
1. 只输出一个 JSON 对象，不得输出任何其他文字、标签或格式
2. 所有 key 和字符串 value 必须使用双引号
3. args 必须是 JSON 对象（可以为空 {{}}），不得写成字符串
4. steps 必须是 JSON 数组，每个元素必须是 JSON 对象（用 {{}} 包裹，不得用 []）
5. 只选择完成任务真正必要的步骤，最多 {max_plan_steps} 步
"""

PLANNER_USER = "用户任务：{task}"

SYNTHESIZER_SYSTEM = """\
你是一个回答助手。根据工具执行结果和对话历史，回答用户的问题。

你必须严格输出以下两种 JSON 格式之一，不得有任何其他内容：

1. 输出最终答案：
{{"action": "answer", "text": "你的完整回答内容"}}

2. 还需要调用一个工具时：
{{"action": "工具名", "args": {{"参数名": "参数值"}}}}

可追加使用的工具：
{tools_description}

【示例】
- 直接回答：{{"action": "answer", "text": "根据您刚才说的，您叫王磊。"}}
- 需要搜索：{{"action": "web_search", "args": {{"query": "搜索词"}}}}
- 需要查记忆：{{"action": "memory_recall", "args": {{"query": "查询词"}}}}

【决策规则】
- 如果对话历史或执行结果中已有足够信息，直接输出 answer，绝对不要再调工具
- 如果当前轮工具执行结果已返回，直接综合结果输出 answer
- 只有在已有信息确实不足以回答时，才调用工具
- 不要对同一个问题反复调用同一工具
- 只输出一个 JSON 对象，不得有任何其他文字
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