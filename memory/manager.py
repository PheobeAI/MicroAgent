# memory/manager.py
"""
MemoryManager — Facade 层（步骤 1 stub）。

已实现：持久化层接入（MemoryStore + SQLiteBackend）、facts/episodes CRUD、生命周期钩子。
占位方法（get_messages_for_llm / append_message / maybe_compress / force_compress）
打印 WARNING 后返回空值；步骤 2-3 逐步实现。
"""
from __future__ import annotations

import logging
from typing import Callable

from core.config import MemoryConfig
from memory.store import Episode, MemoryStore, SQLiteBackend

log = logging.getLogger(__name__)


class MemoryManager:
    def __init__(
        self,
        config: MemoryConfig,
        token_counter: Callable[[list], int],
    ) -> None:
        self._config = config
        self._token_counter = token_counter
        self.store = MemoryStore(SQLiteBackend(config.db_path))
        self.context = None  # 步骤 2 接入 ContextManager

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def on_session_start(self) -> str:
        """
        初始化持久化层，返回 context prefix 字符串。
        步骤 1：连接 DB，返回 ""。步骤 4：组装两层 prefix。
        """
        self.store.load()
        return ""

    def inject_rag_layer(self, user_input: str) -> None:
        """首条用户消息后懒加载第三层 prefix（步骤 4 实现）。"""

    def on_session_end(self) -> None:
        """
        session 结束处理。
        步骤 1：关闭 DB。步骤 3：生成摘要并存储 episode。
        """
        self.store.close()

    # ── 对话管理（步骤 2-3 实现）─────────────────────────────────────────────

    def get_messages_for_llm(self) -> list:
        log.warning("MemoryManager.get_messages_for_llm not yet implemented (Step 2)")
        return []

    def append_message(self, message: object) -> None:
        log.warning("MemoryManager.append_message not yet implemented (Step 2)")

    def maybe_compress(self) -> bool:
        log.warning("MemoryManager.maybe_compress not yet implemented (Step 3)")
        return False

    def force_compress(self) -> None:
        log.warning("MemoryManager.force_compress not yet implemented (Step 3)")

    # ── 事实管理 ──────────────────────────────────────────────────────────────

    def set_fact(self, key: str, value: str) -> None:
        self.store.set_fact(key, value)

    def delete_fact(self, key: str) -> None:
        self.store.delete_fact(key)

    def get_facts(self) -> dict[str, str]:
        return self.store.get_all_facts()

    # ── Episode 管理 ──────────────────────────────────────────────────────────

    def retrieve_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        return self.store.retrieve_episodes(query, top_k=top_k)

    def delete_episode(self, episode_id: int) -> None:
        self.store.delete_episode(episode_id)

    def episode_count(self) -> int:
        return self.store.count_episodes()
