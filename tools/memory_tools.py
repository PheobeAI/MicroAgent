# tools/memory_tools.py
"""Agent 可调用的记忆工具。通过 MemoryManager Facade 操作记忆。"""
from __future__ import annotations

from tools.base import Tool, ToolParam


class MemoryRecallTool(Tool):
    name = "memory_recall"
    description = (
        "检索历史对话记忆，找回过去会话中的决策、结论和上下文。"
        "触发时机：\n"
        "1. 用户明确提到「之前」「上次」「历史」「你还记得吗」等字眼；\n"
        "2. 当前话题可能在过去会话中出现过，需要参考历史结论；\n"
        "3. 用户询问之前讨论过的内容或设置。\n"
        "不应在每轮对话开始时无脑调用，只在确实需要历史背景时使用。"
    )
    parameters = [ToolParam("query", "str", "检索关键词或问题描述")]

    def __init__(self, memory_manager) -> None:
        self._memory = memory_manager

    def __call__(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "错误：query 参数不能为空"
        episodes = self._memory.retrieve_episodes(query, top_k=5)
        if not episodes:
            return "未找到相关历史记忆。"
        lines = []
        for ep in episodes:
            date = ep.ts[:10]
            topics = "、".join(
                t["name"] if isinstance(t, dict) else t
                for t in (ep.topics or [])
            )
            label = f"[{date}][{ep.memory_type}] {topics or '无标签'}"
            lines.append(f"{label}\n{ep.summary}")
        return "\n\n".join(lines)


class MemoryStoreTool(Tool):
    name = "memory_store"
    description = (
        "将重要信息永久写入长期记忆，供后续所有会话使用。"
        "触发时机：\n"
        "1. 用户明确表达意图，如说出「记住」「永远」「始终」「再也不要」「写入记忆」「记一下」等字眼；\n"
        "2. 用户提供个人信息，如姓名、职业、偏好、所在地、习惯等；\n"
        "3. 用户确认某个重要设置或长期偏好（如语言、输出风格、项目名称）。\n"
        "不应在普通问答中随意调用。key 用英文小写下划线（如 user_name），value 简明扼要。"
    )
    parameters = [
        ToolParam("key", "str", "事实的键名，如 user_name / language / project"),
        ToolParam("value", "str", "事实的值"),
    ]

    def __init__(self, memory_manager) -> None:
        self._memory = memory_manager

    def __call__(self, **kwargs) -> str:
        key = kwargs.get("key", "")
        value = kwargs.get("value", "")
        if not key or not value:
            return "错误：key 和 value 参数均不能为空"
        self._memory.set_fact(key, value)
        return f"已记住：{key} = {value}"


class MemoryForgetTool(Tool):
    name = "memory_forget"
    description = "删除一条已存储的事实或历史记忆。删除事实用 key，删除 episode 用 episode_id。"
    parameters = [
        ToolParam("key", "str", "要删除的事实键名（与 episode_id 二选一）", required=False),
        ToolParam("episode_id", "int", "要删除的 episode ID（与 key 二选一）", required=False),
    ]

    def __init__(self, memory_manager) -> None:
        self._memory = memory_manager

    def __call__(self, **kwargs) -> str:
        key = kwargs.get("key", "")
        episode_id = kwargs.get("episode_id")

        if key:
            self._memory.delete_fact(key)
            return f"已删除事实：{key}"
        elif episode_id is not None:
            try:
                eid = int(episode_id)
            except (TypeError, ValueError):
                return f"错误：episode_id 必须是整数，收到 {episode_id!r}"
            self._memory.delete_episode(eid)
            return f"已删除 episode #{eid}"
        else:
            return "错误：必须提供 key 或 episode_id 其中之一"
