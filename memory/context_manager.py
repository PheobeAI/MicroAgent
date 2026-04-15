# memory/context_manager.py
"""ContextManager — Session 内消息缓冲、token 计数与压缩触发。

不持久化，不跨 session；持久化由 MemoryStore 负责。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Any

log = logging.getLogger(__name__)

# 消息类型常量
MSG_NORMAL   = "normal"
MSG_BOUNDARY = "boundary"   # 压缩边界，内含摘要文本
MSG_THINK    = "think"      # 思考内容，不传给 LLM


@dataclass
class Message:
    role: str            # "system" | "user" | "assistant"
    content: str
    msg_type: str = MSG_NORMAL

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class TokenBudget:
    context_window: int
    used_in_current_context: int
    total_consumed_session: int
    compact_count: int


class ContextManager:
    """维护 session 消息列表，驱动 token 预算和压缩。"""

    def __init__(
        self,
        store: Any,                          # MemoryStore
        config: Any,                         # MemoryConfig
        token_counter: Callable[[list], int],
    ) -> None:
        self._store = store
        self._config = config
        self._token_counter = token_counter

        self._buffer: list[Message] = []
        self._turns: int = 0
        self._total_consumed: int = 0
        self._compact_count: int = 0
        self._has_attempted_reactive_compact: bool = False
        self._has_injected_rag: bool = False
        self._prefix: str = ""             # 组装好的记忆前缀，注入 system prompt

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def had_compact(self) -> bool:
        return self._compact_count > 0

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def start_session(self) -> str:
        """组装前两层 context_prefix（话题索引 + 已知事实）并返回字符串。"""
        parts: list[str] = []

        # 层 1：话题索引
        topic_index = self._store.get_topic_index(limit=10)
        if topic_index:
            topics_str = " · ".join(
                f"{t}({n})" for t, n in topic_index.items()
            )
            parts.append(f"## 话题索引\n{topics_str}\n如需检索具体内容，调用 memory_recall 工具。")

        # 层 2：已知事实
        facts = self._store.get_all_facts()
        if facts:
            facts_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
            parts.append(f"## 已知事实\n{facts_lines}")

        if parts:
            self._prefix = "[记忆]\n" + "\n\n".join(parts) + "\n[/记忆]"
        else:
            self._prefix = ""

        return self._prefix

    def inject_rag_layer(self, user_input: str) -> None:
        """首条用户消息到达后懒加载第三层（相关历史）。只执行一次。"""
        if self._has_injected_rag:
            return
        self._has_injected_rag = True

        max_ep = getattr(self._config, "max_episodes_in_prefix", 3)
        if max_ep == 0:
            return

        episodes = self._store.retrieve_episodes(user_input, top_k=max_ep)
        if not episodes:
            return

        lines = []
        for ep in episodes:
            date = ep.ts[:10]
            topics = "、".join(
                t["name"] if isinstance(t, dict) else t
                for t in (ep.topics or [])
            )
            label = f"[{date}] {topics or ep.memory_type}"
            lines.append(f"- {label}：{ep.summary[:120]}")

        rag_text = "## 相关历史（自动检索）\n" + "\n".join(lines)

        # 追加到已有 prefix
        if self._prefix:
            self._prefix = self._prefix.replace(
                "[/记忆]", f"\n\n{rag_text}\n[/记忆]"
            )
        else:
            self._prefix = f"[记忆]\n{rag_text}\n[/记忆]"

        log.debug("RAG layer injected: %d episodes", len(episodes))

    def end_session(self, model: Any = None) -> None:
        """Session 结束：生成摘要并存入 MemoryStore。"""
        min_turns = getattr(self._config, "min_turns_to_save", 2)
        if self._turns < min_turns:
            log.debug("Session too short (%d turns), skipping save", self._turns)
            return

        summary, topics, memory_type = self._generate_summary(model)
        from memory.store import calc_importance
        importance = calc_importance(summary, memory_type, self._turns, self.had_compact)
        self._store.save_episode(
            summary=summary,
            topics=topics,
            turns=self._turns,
            had_compact=self.had_compact,
            memory_type=memory_type,
            importance=importance,
        )
        log.info("Session saved: %d turns, type=%s", self._turns, memory_type)

    def _generate_summary(self, model: Any) -> tuple[str, list, str]:
        """用 LLM 生成 {summary, topics, type}。失败时回退到原文拼接。"""
        from memory.store import detect_memory_type

        msgs = self.get_messages_for_llm()
        raw_text = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in msgs[-20:]
        )

        if model is None:
            # 无 LLM 时直接截取原文
            summary = raw_text[:300]
            return summary, [], detect_memory_type(summary)

        try:
            prompt = [
                {"role": "system", "content": (
                    "分析以下对话，输出 JSON（不要其他内容）：\n"
                    '{"summary": "2-3句话的摘要", "topics": ["词组1", "词组2"], '
                    '"type": "decision|milestone|problem|preference|general"}\n'
                    "topic 要求：3-5个，每个3-15字，具体可召回。"
                )},
                {"role": "user", "content": raw_text},
            ]
            import json as _json
            raw = model.generate(prompt)
            # strip markdown code blocks if present
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = _json.loads(raw)
            summary = data.get("summary", raw_text[:300])
            topics_raw = data.get("topics", [])
            topics = [{"name": t, "weight": 1.0} for t in topics_raw if isinstance(t, str)]
            memory_type = data.get("type", "general")
            return summary, topics, memory_type
        except Exception as e:
            log.error("Summary generation failed: %s — using raw text fallback", e)
            summary = raw_text[:300]
            return summary, [], detect_memory_type(summary)

    # ── 消息管理 ──────────────────────────────────────────────────────────────

    def append_message(self, message: Message) -> None:
        """追加消息到 buffer，assistant 消息完成一轮对话计数。"""
        self._buffer.append(message)
        if message.role == "assistant" and message.msg_type == MSG_NORMAL:
            self._turns += 1

    def get_messages_for_llm(self) -> list[dict]:
        """返回发给 LLM 的消息列表：BOUNDARY 之后切片，过滤 MSG_THINK。"""
        # 找最后一个 BOUNDARY
        boundary_idx = None
        for i in reversed(range(len(self._buffer))):
            if self._buffer[i].msg_type == MSG_BOUNDARY:
                boundary_idx = i
                break

        if boundary_idx is not None:
            slice_ = self._buffer[boundary_idx:]
        else:
            slice_ = self._buffer

        return [m.to_dict() for m in slice_ if m.msg_type != MSG_THINK]

    # ── Token 预算 ────────────────────────────────────────────────────────────

    def token_usage(self) -> TokenBudget:
        msgs = self.get_messages_for_llm()
        used = self._token_counter(msgs)
        return TokenBudget(
            context_window=self._config.context_window_tokens,
            used_in_current_context=used,
            total_consumed_session=self._total_consumed + used,
            compact_count=self._compact_count,
        )

    # ── 压缩 ──────────────────────────────────────────────────────────────────

    def maybe_compress(self) -> bool:
        """检查是否超过阈值，超过则压缩。返回是否触发了压缩。"""
        budget = self.token_usage()
        ratio = budget.used_in_current_context / budget.context_window
        # 兼容 compress_threshold 和 compression_threshold 两种 config 字段名
        threshold = getattr(self._config, "compress_threshold",
                            getattr(self._config, "compression_threshold", 0.8))
        if ratio >= threshold:
            self.force_compress()
            return True
        return False

    def force_compress(self, model: Any = None) -> None:
        """强制压缩：生成摘要，插入 BOUNDARY，丢弃旧消息。"""
        keep = getattr(self._config, "keep_recent_turns", 5)
        msgs = self.get_messages_for_llm()

        # 生成摘要
        summary_text = self._compress_summary(msgs, model)

        # 找 boundary_idx 以计算消耗
        budget_before = self.token_usage()
        self._total_consumed += budget_before.used_in_current_context

        # 保留最近 keep 轮（keep*2 条消息，user+assistant）
        keep_msgs = self._buffer[-keep * 2:]

        boundary = Message(
            role="assistant",
            content=f"[摘要]{summary_text}",
            msg_type=MSG_BOUNDARY,
        )
        self._buffer = [boundary] + list(keep_msgs)
        self._compact_count += 1
        self._has_attempted_reactive_compact = False
        log.info("Compacted: kept %d turns, compact_count=%d", keep, self._compact_count)

    def reactive_compress(self, model: Any = None) -> bool:
        """上下文溢出兜底压缩。防无限循环：只执行一次。"""
        if self._has_attempted_reactive_compact:
            log.error("Reactive compress already attempted, skipping to prevent loop")
            return False
        self._has_attempted_reactive_compact = True
        self.force_compress(model)
        return True

    def _compress_summary(self, msgs: list[dict], model: Any) -> str:
        """为压缩生成摘要文本。无 LLM 时回退到截取原文。"""
        if model is None:
            raw = "\n".join(f"{m['role']}: {m['content'][:100]}" for m in msgs[-10:])
            return raw[:400]
        try:
            instructions = getattr(self._config, "pre_compact_instructions", "")
            system = (
                "请用2-4句话总结以下对话的核心内容，保留关键决定、文件路径和工具结果。"
                + (f"\n额外要求：{instructions}" if instructions else "")
            )
            prompt = [
                {"role": "system", "content": system},
                *msgs[-20:],
                {"role": "user", "content": "请生成摘要。"},
            ]
            return model.generate(prompt).strip()
        except Exception as e:
            log.error("Compress summary failed: %s", e)
            raw = "\n".join(f"{m['role']}: {m['content'][:100]}" for m in msgs[-10:])
            return raw[:400]
