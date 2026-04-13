# memory/store.py
from __future__ import annotations

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── Episode ───────────────────────────────────────────────────────────────────

@dataclass
class Episode:
    """一条持久化的会话记忆记录。"""
    ts: str                                          # ISO 8601 UTC 时间戳
    summary: str                                     # 会话摘要文本
    topics: list[dict] = field(default_factory=list)
    # topics 格式：[{"name": "CUDA构建", "weight": 0.9}, ...]
    # weight 默认 1.0；步骤 5 由算法赋值
    id: Optional[int] = None    # DB 主键，写入前为 None
    turns: int = 0
    had_compact: bool = False
    memory_type: str = "general"  # decision|preference|milestone|problem|general
    importance: float = 0.5       # 重要性评分 0.0-1.0


# ── StorageBackend ABC ────────────────────────────────────────────────────────

class StorageBackend(ABC):
    """持久化后端抽象。实现此接口可替换底层存储（SQLite / 加密 DB 等）。"""

    @abstractmethod
    def save_episode(self, episode: Episode) -> int:
        """持久化一条 episode，返回数据库分配的 id。"""

    @abstractmethod
    def list_episodes(self, limit: int = 50) -> list[Episode]:
        """按时间倒序返回最近 limit 条 episodes。"""

    @abstractmethod
    def search_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        """检索 top_k 条 episodes（步骤 5 升级为 BM25）。"""

    @abstractmethod
    def save_fact(self, key: str, value: str) -> None:
        """插入或更新一条 fact（upsert）。"""

    @abstractmethod
    def get_all_facts(self) -> dict[str, str]:
        """返回 facts 表全量数据 {key: value}。"""

    @abstractmethod
    def delete_fact(self, key: str) -> None:
        """删除指定 key；不存在时静默忽略。"""

    @abstractmethod
    def delete_episode(self, episode_id: int) -> None:
        """删除指定 id；不存在时静默忽略。"""

    @abstractmethod
    def count_episodes(self) -> int:
        """返回 episodes 总行数。"""

    @abstractmethod
    def close(self) -> None:
        """释放底层资源（幂等）。"""


# ── SQLiteBackend ─────────────────────────────────────────────────────────────

class SQLiteBackend(StorageBackend):
    """SQLite 实现。WAL 模式支持并发读，事务保证原子写。"""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS episodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT    NOT NULL,
        summary     TEXT    NOT NULL,
        topics      TEXT    NOT NULL DEFAULT '[]',
        turns       INTEGER NOT NULL DEFAULT 0,
        had_compact INTEGER NOT NULL DEFAULT 0,
        memory_type TEXT    NOT NULL DEFAULT 'general',
        importance  REAL    NOT NULL DEFAULT 0.5
    );
    CREATE TABLE IF NOT EXISTS facts (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ── Episodes ──────────────────────────────────────────────────────────────

    def save_episode(self, episode: Episode) -> int:
        topics_json = json.dumps(episode.topics, ensure_ascii=False)
        cur = self._conn.execute(  # type: ignore[union-attr]
            "INSERT INTO episodes (ts, summary, topics, turns, had_compact, memory_type, importance)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (episode.ts, episode.summary, topics_json, episode.turns,
             int(episode.had_compact), episode.memory_type, episode.importance),
        )
        self._conn.commit()  # type: ignore[union-attr]
        return cur.lastrowid  # type: ignore[return-value]

    def list_episodes(self, limit: int = 50) -> list[Episode]:
        rows = self._conn.execute(  # type: ignore[union-attr]
            "SELECT id, ts, summary, topics, turns, had_compact, memory_type, importance"
            " FROM episodes ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def search_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        # 步骤 5 升级为 BM25 + 时间衰减；当前退化为时间倒序
        return self.list_episodes(limit=top_k)

    def delete_episode(self, episode_id: int) -> None:
        self._conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))  # type: ignore[union-attr]
        self._conn.commit()  # type: ignore[union-attr]

    def count_episodes(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()  # type: ignore[union-attr]
        return row[0]

    # ── Facts ─────────────────────────────────────────────────────────────────

    def save_fact(self, key: str, value: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(  # type: ignore[union-attr]
            "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, ts),
        )
        self._conn.commit()  # type: ignore[union-attr]

    def get_all_facts(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM facts").fetchall()  # type: ignore[union-attr]
        return {r[0]: r[1] for r in rows}

    def delete_fact(self, key: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))  # type: ignore[union-attr]
        self._conn.commit()  # type: ignore[union-attr]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_episode(row: tuple) -> Episode:
        ep_id, ts, summary, topics_json, turns, had_compact, memory_type, importance = row
        return Episode(
            id=ep_id,
            ts=ts,
            summary=summary,
            topics=json.loads(topics_json),
            turns=turns,
            had_compact=bool(had_compact),
            memory_type=memory_type,
            importance=importance,
        )


# ── MemoryStore ───────────────────────────────────────────────────────────────

class MemoryStore:
    """业务接口包装层。调用方只与此类交互，不直接接触 StorageBackend。"""

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def load(self) -> None:
        """生命周期钩子，预留（当前无操作）。"""

    def close(self) -> None:
        """关闭底层 backend 连接。"""
        self._backend.close()

    # ── Episodes ──────────────────────────────────────────────────────────────

    def save_episode(
        self,
        summary: str,
        topics: list[dict],
        turns: int,
        had_compact: bool,
        memory_type: str,
        importance: float,
    ) -> None:
        """内部生成 ts（UTC ISO 8601），调用方无需传时间戳。"""
        ts = datetime.now(timezone.utc).isoformat()
        ep = Episode(
            ts=ts,
            summary=summary,
            topics=topics,
            turns=turns,
            had_compact=had_compact,
            memory_type=memory_type,
            importance=importance,
        )
        self._backend.save_episode(ep)

    def retrieve_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        """检索相关 episodes（步骤 5 升级为 BM25 混合检索）。"""
        return self._backend.search_episodes(query, top_k=top_k)

    def get_topic_index(self, limit: int = 10) -> dict[str, float]:
        """
        聚合所有 episodes 的 topics，按 weight 累加降序返回 top limit 个。
        返回格式：{"项目架构": 1.8, "CUDA构建": 1.5, ...}
        """
        all_episodes = self._backend.list_episodes(limit=100_000)
        counter: Counter[str] = Counter()
        for ep in all_episodes:
            for t in ep.topics:
                counter[t["name"]] += t.get("weight", 1.0)
        return dict(counter.most_common(limit))

    def delete_episode(self, episode_id: int) -> None:
        self._backend.delete_episode(episode_id)

    def count_episodes(self) -> int:
        return self._backend.count_episodes()

    # ── Facts ─────────────────────────────────────────────────────────────────

    def set_fact(self, key: str, value: str) -> None:
        self._backend.save_fact(key, value)

    def get_all_facts(self) -> dict[str, str]:
        return self._backend.get_all_facts()

    def delete_fact(self, key: str) -> None:
        self._backend.delete_fact(key)
