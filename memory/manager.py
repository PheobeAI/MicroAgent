# memory/manager.py
"""MemoryManager — Facade 层，协调 MemoryStore 与 ContextManager。"""
from __future__ import annotations

import logging
from typing import Callable

from core.config import MemoryConfig
from memory.context_manager import ContextManager, Message, MSG_NORMAL, TokenBudget
from memory.store import Episode, MemoryStore, SQLiteBackend

log = logging.getLogger(__name__)


class MemoryManager:
    """
    对 cli/app.py 和 core/agent.py 暴露统一接口，屏蔽内部拆分细节。
    调用方只与此类交互，不直接接触 MemoryStore 或 ContextManager。
    """

    def __init__(
        self,
        config: MemoryConfig,
        token_counter: Callable[[list], int],
    ) -> None:
        self._config = config
        self.store = MemoryStore(SQLiteBackend(config.db_path))
        self.context = ContextManager(self.store, config, token_counter)

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def on_session_start(self) -> str:
        """连接 DB，组装前两层 context_prefix，返回字符串。"""
        self.store.load()
        return self.context.start_session()

    def inject_rag_layer(self, user_input: str) -> None:
        """首条用户消息到达后懒加载第三层（相关历史）。"""
        self.context.inject_rag_layer(user_input)

    def on_session_end(self, model=None) -> None:
        """Session 结束：生成摘要并存储 episode，关闭 DB 连接。
        
        即使被 KeyboardInterrupt 或其他异常中断也不抛出，确保 DB 正常关闭。
        """
        try:
            self.context.end_session(model=model)
        except KeyboardInterrupt:
            log.warning("Session end interrupted by user, skipping summary generation")
        except Exception as e:
            log.error("Session end failed: %s", e)
        finally:
            try:
                self.store.close()
            except Exception as e:
                log.error("Store close failed: %s", e)

    # ── 对话管理 ──────────────────────────────────────────────────────────────

    def get_messages_for_llm(self) -> list[dict]:
        return self.context.get_messages_for_llm()

    def append_user(self, content: str) -> None:
        self.context.append_message(Message(role="user", content=content))

    def append_assistant(self, content: str) -> None:
        self.context.append_message(Message(role="assistant", content=content))

    def maybe_compress(self, model=None) -> bool:
        return self.context.maybe_compress()

    def force_compress(self, model=None) -> None:
        self.context.force_compress(model=model)

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

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    def token_usage(self) -> TokenBudget:
        return self.context.token_usage()

    @property
    def prefix(self) -> str:
        """当前记忆前缀文本（含所有已注入的层）。"""
        return self.context._prefix