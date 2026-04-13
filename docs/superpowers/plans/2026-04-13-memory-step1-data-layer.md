# Memory Step 1 — 数据层：`memory/` 骨架 + SQLite 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `memory/` 模块的持久化层（`StorageBackend` 抽象 + `SQLiteBackend` 实现 + `MemoryStore` 业务包装 + `MemoryManager` stub），并在 `core/config.py` 新增 `MemoryConfig`，配套完整单元测试。

**Architecture:** 三层结构：`StorageBackend`（ABC）→ `SQLiteBackend`（WAL 模式 SQLite CRUD 实现）→ `MemoryStore`（业务接口包装）。`MemoryManager` 本步骤只做空实现占位，不接入 `ContextManager`。依赖方向单向，无循环引用。

**Tech Stack:** Python 内置 `sqlite3`（WAL 模式），`pydantic`（`MemoryConfig`），`pytest`（测试框架）。零新增依赖。

**设计文档参考：** `docs/memory-design.md` §「MemoryStore — 持久化层」、§「步骤 1」

---

## 文件变更清单

| 操作 | 路径 | 说明 |
|---|---|---|
| 新建 | `memory/__init__.py` | 包入口，导出 `MemoryManager` |
| 新建 | `memory/store.py` | `Episode` dataclass、`StorageBackend` ABC、`SQLiteBackend`、`MemoryStore` |
| 新建 | `memory/manager.py` | `MemoryManager` stub（空实现占位） |
| 新建 | `tests/memory/__init__.py` | 测试包 |
| 新建 | `tests/memory/test_store.py` | `SQLiteBackend` + `MemoryStore` 单元测试 |
| 修改 | `core/config.py` | 新增 `MemoryConfig`、在 `AppConfig` 中加 `memory` 字段 |
| 修改 | `tests/test_config.py` | 新增 `MemoryConfig` 默认值断言 |

---

## Task 1：`MemoryConfig` 加入 `core/config.py`

**Files:**
- Modify: `core/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 末尾追加：

```python
def test_memory_config_defaults():
    config = load_config(Path("/nonexistent/config.yaml"))
    m = config.memory
    assert m.enabled is True
    assert m.db_path == r"memory\microagent.db"
    assert m.context_window_tokens == 131072
    assert m.compression_threshold == 0.80
    assert m.keep_recent_turns == 6
    assert m.post_compact_reserve == 40960
    assert m.max_episodes_in_prefix == 5
    assert m.pre_compact_instructions == ""
    assert m.max_tool_output_chars == 8000
    assert m.min_turns_to_save == 3
    assert m.retrieval.bm25_weight == 0.5
    assert m.retrieval.recency_weight == 0.3
    assert m.retrieval.importance_weight == 0.2
    assert m.retrieval.decay_rate == 0.1


def test_memory_config_yaml_override(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "memory:\n  enabled: false\n  max_episodes_in_prefix: 0\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.memory.enabled is False
    assert config.memory.max_episodes_in_prefix == 0
    assert config.memory.compression_threshold == 0.80  # default preserved
```

- [ ] **Step 2: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/test_config.py::test_memory_config_defaults -v
```

期望：`FAILED`，报 `AttributeError: 'AppConfig' object has no attribute 'memory'`

- [ ] **Step 3: 在 `core/config.py` 中实现 `MemoryConfig`**

在 `RuntimeConfig` 类定义**之前**插入以下代码：

```python
class RetrievalConfig(BaseModel):
    bm25_weight: float = 0.5
    recency_weight: float = 0.3
    importance_weight: float = 0.2
    decay_rate: float = 0.1


class MemoryConfig(BaseModel):
    enabled: bool = True
    db_path: str = r"memory\microagent.db"
    context_window_tokens: int = 131072
    compression_threshold: float = 0.80
    keep_recent_turns: int = 6
    post_compact_reserve: int = 40960
    max_episodes_in_prefix: int = 5
    pre_compact_instructions: str = ""
    max_tool_output_chars: int = 8000
    min_turns_to_save: int = 3
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
```

然后在 `AppConfig` 中加一行：

```python
class AppConfig(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)   # ← 新增
```

- [ ] **Step 4: 运行测试，确认通过**

```
.venv\Scripts\pytest tests/test_config.py -v
```

期望：所有用例 `PASSED`

- [ ] **Step 5: Commit**

```
git add core/config.py tests/test_config.py
git commit -m "feat(config): add MemoryConfig and RetrievalConfig"
```

---

## Task 2：`Episode` dataclass + `StorageBackend` ABC

**Files:**
- Create: `memory/__init__.py`
- Create: `memory/store.py`
- Create: `tests/memory/__init__.py`
- Create: `tests/memory/test_store.py`

- [ ] **Step 1: 创建包入口**

新建 `memory/__init__.py`（空文件，内容如下）：

```python
# memory/__init__.py
from memory.manager import MemoryManager

__all__ = ["MemoryManager"]
```

新建 `tests/memory/__init__.py`（空文件）：

```python
```

- [ ] **Step 2: 写失败测试（Episode dataclass）**

新建 `tests/memory/test_store.py`：

```python
# tests/memory/test_store.py
import json
from datetime import datetime, timezone

import pytest

from memory.store import Episode


def test_episode_fields():
    ep = Episode(
        id=1,
        ts="2026-04-13T10:00:00+00:00",
        summary="测试摘要",
        topics=["CUDA构建", "CI调试"],
        turns=5,
        had_compact=False,
        memory_type="general",
        importance=0.5,
    )
    assert ep.id == 1
    assert ep.summary == "测试摘要"
    assert ep.topics == ["CUDA构建", "CI调试"]
    assert ep.turns == 5
    assert ep.had_compact is False
    assert ep.memory_type == "general"
    assert ep.importance == 0.5


def test_episode_default_id():
    ep = Episode(
        ts="2026-04-13T10:00:00+00:00",
        summary="摘要",
        topics=[],
    )
    assert ep.id is None
    assert ep.turns == 0
    assert ep.had_compact is False
    assert ep.memory_type == "general"
    assert ep.importance == 0.5
```

- [ ] **Step 3: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/memory/test_store.py::test_episode_fields -v
```

期望：`FAILED`，报 `ModuleNotFoundError: No module named 'memory'`

- [ ] **Step 4: 实现 `Episode` dataclass**

新建 `memory/store.py`，内容如下（只写到 `Episode`，后续 Task 继续追加）：

```python
# memory/store.py
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Episode:
    """一条持久化的会话记忆记录。"""
    ts: str                          # ISO 8601 时间戳
    summary: str                     # 会话摘要文本
    topics: list[str] = field(default_factory=list)   # 关键词列表
    id: Optional[int] = None         # 数据库主键，写入前为 None
    turns: int = 0                   # 本次 session 对话轮数
    had_compact: bool = False        # 是否触发过压缩
    memory_type: str = "general"     # decision|preference|milestone|problem|general
    importance: float = 0.5          # 重要性评分 0.0-1.0
```

- [ ] **Step 5: 运行测试，确认通过**

```
.venv\Scripts\pytest tests/memory/test_store.py -v
```

期望：`test_episode_fields` 和 `test_episode_default_id` 均 `PASSED`

- [ ] **Step 6: Commit**

```
git add memory/__init__.py memory/store.py tests/memory/__init__.py tests/memory/test_store.py
git commit -m "feat(memory): add Episode dataclass"
```

---

## Task 3：`StorageBackend` ABC

**Files:**
- Modify: `memory/store.py`（追加）
- Modify: `tests/memory/test_store.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/memory/test_store.py` 末尾追加：

```python
from memory.store import StorageBackend


def test_storage_backend_is_abstract():
    """StorageBackend 不能直接实例化，必须实现所有抽象方法。"""
    with pytest.raises(TypeError):
        StorageBackend()  # type: ignore


def test_storage_backend_subclass_must_implement_all_methods():
    """子类若未实现所有方法，实例化时应抛 TypeError。"""
    class IncompleteBackend(StorageBackend):
        pass  # 故意不实现任何方法

    with pytest.raises(TypeError):
        IncompleteBackend()
```

- [ ] **Step 2: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/memory/test_store.py::test_storage_backend_is_abstract -v
```

期望：`FAILED`，报 `ImportError: cannot import name 'StorageBackend'`

- [ ] **Step 3: 在 `memory/store.py` 中追加 `StorageBackend`**

在 `Episode` dataclass **之后**追加：

```python
class StorageBackend(ABC):
    """持久化后端抽象。实现此接口可替换底层存储（SQLite / 加密 DB / 云端等）。"""

    @abstractmethod
    def save_episode(self, episode: Episode) -> int:
        """持久化一条 episode，返回数据库分配的 id。"""

    @abstractmethod
    def list_episodes(self, limit: int = 50) -> list[Episode]:
        """按时间倒序返回最近 limit 条 episodes。"""

    @abstractmethod
    def search_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        """检索与 query 最相关的 top_k 条 episodes（当前实现：时间倒序；步骤 5 升级 BM25）。"""

    @abstractmethod
    def save_fact(self, key: str, value: str) -> None:
        """插入或更新一条 fact（upsert）。"""

    @abstractmethod
    def get_all_facts(self) -> dict[str, str]:
        """返回 facts 表全量数据 {key: value}。"""

    @abstractmethod
    def delete_fact(self, key: str) -> None:
        """删除指定 key 的 fact；key 不存在时静默忽略。"""

    @abstractmethod
    def delete_episode(self, episode_id: int) -> None:
        """删除指定 id 的 episode；id 不存在时静默忽略。"""

    @abstractmethod
    def count_episodes(self) -> int:
        """返回 episodes 表总行数。"""
```

- [ ] **Step 4: 运行测试，确认通过**

```
.venv\Scripts\pytest tests/memory/test_store.py -v
```

期望：所有用例 `PASSED`

- [ ] **Step 5: Commit**

```
git add memory/store.py tests/memory/test_store.py
git commit -m "feat(memory): add StorageBackend ABC"
```

---

## Task 4：`SQLiteBackend` — schema 建表与 CRUD

**Files:**
- Modify: `memory/store.py`（追加）
- Modify: `tests/memory/test_store.py`（追加）

- [ ] **Step 1: 写失败测试（建表 + 基础 CRUD）**

在 `tests/memory/test_store.py` 末尾追加：

```python
from memory.store import SQLiteBackend


@pytest.fixture
def backend(tmp_path):
    """每个测试用例使用独立的临时数据库。"""
    db = SQLiteBackend(str(tmp_path / "test.db"))
    yield db
    db._conn.close()


def test_sqlite_save_and_list_episode(backend):
    ep = Episode(
        ts="2026-04-13T10:00:00+00:00",
        summary="CUDA 构建成功",
        topics=["CUDA构建", "CI"],
        turns=10,
        had_compact=False,
        memory_type="milestone",
        importance=0.8,
    )
    returned_id = backend.save_episode(ep)
    assert isinstance(returned_id, int)
    assert returned_id > 0

    episodes = backend.list_episodes(limit=10)
    assert len(episodes) == 1
    saved = episodes[0]
    assert saved.id == returned_id
    assert saved.summary == "CUDA 构建成功"
    assert saved.topics == ["CUDA构建", "CI"]
    assert saved.turns == 10
    assert saved.had_compact is False
    assert saved.memory_type == "milestone"
    assert abs(saved.importance - 0.8) < 1e-6


def test_sqlite_list_episodes_order(backend):
    """list_episodes 应按时间倒序返回。"""
    backend.save_episode(Episode(ts="2026-04-11T10:00:00+00:00", summary="旧的", topics=[]))
    backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00", summary="新的", topics=[]))
    episodes = backend.list_episodes(limit=10)
    assert episodes[0].summary == "新的"
    assert episodes[1].summary == "旧的"


def test_sqlite_list_episodes_limit(backend):
    for i in range(5):
        backend.save_episode(Episode(ts=f"2026-04-{i+1:02d}T10:00:00+00:00",
                                     summary=f"摘要{i}", topics=[]))
    episodes = backend.list_episodes(limit=3)
    assert len(episodes) == 3


def test_sqlite_delete_episode(backend):
    ep_id = backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00",
                                          summary="待删除", topics=[]))
    backend.delete_episode(ep_id)
    assert backend.count_episodes() == 0


def test_sqlite_delete_episode_nonexistent_silent(backend):
    """删除不存在的 id 不应抛异常。"""
    backend.delete_episode(9999)  # should not raise


def test_sqlite_count_episodes(backend):
    assert backend.count_episodes() == 0
    backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00", summary="x", topics=[]))
    assert backend.count_episodes() == 1


def test_sqlite_save_and_get_facts(backend):
    backend.save_fact("language", "zh")
    backend.save_fact("user_name", "Pheobe")
    facts = backend.get_all_facts()
    assert facts["language"] == "zh"
    assert facts["user_name"] == "Pheobe"


def test_sqlite_save_fact_upsert(backend):
    backend.save_fact("language", "zh")
    backend.save_fact("language", "en")  # 覆盖
    facts = backend.get_all_facts()
    assert facts["language"] == "en"
    assert len(facts) == 1


def test_sqlite_delete_fact(backend):
    backend.save_fact("key1", "val1")
    backend.delete_fact("key1")
    assert backend.get_all_facts() == {}


def test_sqlite_delete_fact_nonexistent_silent(backend):
    """删除不存在的 key 不应抛异常。"""
    backend.delete_fact("nonexistent")  # should not raise


def test_sqlite_wal_mode(backend):
    """确认 WAL journal mode 已启用。"""
    row = backend._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
```

- [ ] **Step 2: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/memory/test_store.py::test_sqlite_save_and_list_episode -v
```

期望：`FAILED`，报 `ImportError: cannot import name 'SQLiteBackend'`

- [ ] **Step 3: 在 `memory/store.py` 中追加 `SQLiteBackend`**

在 `StorageBackend` 之后追加：

```python
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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ── Episodes ─────────────────────────────────────────────────────────────

    def save_episode(self, episode: Episode) -> int:
        topics_json = json.dumps(episode.topics, ensure_ascii=False)
        cur = self._conn.execute(
            "INSERT INTO episodes (ts, summary, topics, turns, had_compact, memory_type, importance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (episode.ts, episode.summary, topics_json,
             episode.turns, int(episode.had_compact),
             episode.memory_type, episode.importance),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_episodes(self, limit: int = 50) -> list[Episode]:
        rows = self._conn.execute(
            "SELECT id, ts, summary, topics, turns, had_compact, memory_type, importance "
            "FROM episodes ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def search_episodes(self, query: str, top_k: int = 5) -> list[Episode]:
        # 当前实现：时间倒序（步骤 5 升级为 BM25 + 时间衰减混合检索）
        return self.list_episodes(limit=top_k)

    def delete_episode(self, episode_id: int) -> None:
        self._conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
        self._conn.commit()

    def count_episodes(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
        return row[0]

    # ── Facts ─────────────────────────────────────────────────────────────────

    def save_fact(self, key: str, value: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, ts),
        )
        self._conn.commit()

    def get_all_facts(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM facts").fetchall()
        return {r[0]: r[1] for r in rows}

    def delete_fact(self, key: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        self._conn.commit()

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
```

- [ ] **Step 4: 运行测试，确认全部通过**

```
.venv\Scripts\pytest tests/memory/test_store.py -v
```

期望：所有 `SQLiteBackend` 相关用例 `PASSED`

- [ ] **Step 5: Commit**

```
git add memory/store.py tests/memory/test_store.py
git commit -m "feat(memory): implement SQLiteBackend with WAL mode and full CRUD"
```

---

## Task 5：`MemoryStore` 业务包装层

**Files:**
- Modify: `memory/store.py`（追加）
- Modify: `tests/memory/test_store.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/memory/test_store.py` 末尾追加：

```python
from memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(SQLiteBackend(str(tmp_path / "store_test.db")))
    s.load()
    yield s
    s.close()


def test_store_save_and_retrieve_episode(store):
    store.save_episode(
        summary="项目初始化完成",
        topics=["项目架构", "初始化"],
        turns=3,
        had_compact=False,
        memory_type="milestone",
        importance=0.8,
    )
    episodes = store.retrieve_episodes(query="初始化", top_k=5)
    assert len(episodes) == 1
    assert episodes[0].summary == "项目初始化完成"
    assert episodes[0].topics == ["项目架构", "初始化"]


def test_store_get_topic_index_counts(store):
    store.save_episode(summary="A", topics=["CUDA构建", "CI"], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)
    store.save_episode(summary="B", topics=["CUDA构建", "项目架构"], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)
    store.save_episode(summary="C", topics=["项目架构"], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)

    index = store.get_topic_index(limit=10)
    assert index["CUDA构建"] == 2
    assert index["项目架构"] == 2
    assert index["CI"] == 1


def test_store_get_topic_index_respects_limit(store):
    for i in range(15):
        store.save_episode(summary=f"ep{i}", topics=[f"topic{i}"], turns=1,
                           had_compact=False, memory_type="general", importance=0.5)
    index = store.get_topic_index(limit=10)
    assert len(index) == 10


def test_store_facts_crud(store):
    store.set_fact("language", "zh")
    assert store.get_all_facts()["language"] == "zh"

    store.set_fact("language", "en")
    assert store.get_all_facts()["language"] == "en"

    store.delete_fact("language")
    assert "language" not in store.get_all_facts()


def test_store_count_episodes(store):
    assert store.count_episodes() == 0
    store.save_episode(summary="x", topics=[], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)
    assert store.count_episodes() == 1


def test_store_delete_episode(store):
    store.save_episode(summary="删我", topics=[], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)
    episodes = store.retrieve_episodes(query="", top_k=5)
    ep_id = episodes[0].id
    store.delete_episode(ep_id)
    assert store.count_episodes() == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/memory/test_store.py::test_store_save_and_retrieve_episode -v
```

期望：`FAILED`，报 `ImportError: cannot import name 'MemoryStore'`

- [ ] **Step 3: 在 `memory/store.py` 末尾追加 `MemoryStore`**

```python
class MemoryStore:
    """业务接口包装层。调用方只与此类交互，不直接接触 StorageBackend。"""

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def load(self) -> None:
        """预留生命周期钩子（当前实现无需初始化操作）。"""

    def close(self) -> None:
        """预留生命周期钩子（当前实现无需清理操作）。"""

    # ── Episodes ─────────────────────────────────────────────────────────────

    def save_episode(
        self,
        summary: str,
        topics: list[str],
        turns: int,
        had_compact: bool,
        memory_type: str,
        importance: float,
    ) -> None:
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
        """检索相关 episodes（当前：时间倒序；步骤 5 升级为 BM25 混合检索）。"""
        return self._backend.search_episodes(query, top_k=top_k)

    def get_topic_index(self, limit: int = 10) -> dict[str, int]:
        """
        聚合所有 episodes 的 topics，按出现频次降序返回 top `limit` 个。
        返回格式：{"CUDA构建": 3, "项目架构": 5, ...}
        """
        from collections import Counter
        all_episodes = self._backend.list_episodes(limit=10000)
        counter: Counter[str] = Counter()
        for ep in all_episodes:
            counter.update(ep.topics)
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
```

- [ ] **Step 4: 运行测试，确认全部通过**

```
.venv\Scripts\pytest tests/memory/test_store.py -v
```

期望：所有用例 `PASSED`

- [ ] **Step 5: Commit**

```
git add memory/store.py tests/memory/test_store.py
git commit -m "feat(memory): implement MemoryStore business wrapper"
```

---

## Task 6：`MemoryManager` stub

**Files:**
- Create: `memory/manager.py`
- Create: `tests/memory/test_manager.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/memory/test_manager.py`：

```python
# tests/memory/test_manager.py
import pytest
from memory.manager import MemoryManager
from core.config import MemoryConfig


@pytest.fixture
def manager(tmp_path):
    cfg = MemoryConfig(db_path=str(tmp_path / "manager_test.db"))
    mgr = MemoryManager(config=cfg, token_counter=lambda msgs: 0)
    yield mgr
    mgr.on_session_end()


def test_manager_instantiates(manager):
    """MemoryManager 能正常实例化，内部 store 和 context 存在。"""
    assert manager.store is not None
    assert manager.context is None   # 步骤 2 才接入 ContextManager


def test_manager_on_session_start_returns_string(manager):
    prefix = manager.on_session_start()
    assert isinstance(prefix, str)


def test_manager_on_session_end_does_not_raise(manager):
    manager.on_session_start()
    manager.on_session_end()  # should not raise


def test_manager_set_get_delete_fact(manager):
    manager.set_fact("user_name", "Pheobe")
    assert manager.get_facts()["user_name"] == "Pheobe"
    manager.delete_fact("user_name")
    assert "user_name" not in manager.get_facts()


def test_manager_episode_count(manager):
    assert manager.episode_count() == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```
.venv\Scripts\pytest tests/memory/test_manager.py::test_manager_instantiates -v
```

期望：`FAILED`，报 `ModuleNotFoundError: No module named 'memory.manager'`

- [ ] **Step 3: 实现 `memory/manager.py` stub**

新建 `memory/manager.py`：

```python
# memory/manager.py
"""
MemoryManager — Facade 层。

当前为 步骤 1 stub：
- 持久化层（MemoryStore + SQLiteBackend）已接入
- ContextManager 尚未实现（步骤 2 接入）
- get_messages_for_llm / append_message / compress 方法均为占位，步骤 2 实现

调用方（cli/app.py、core/agent.py）只与此类交互，无需感知内部拆分。
"""
from __future__ import annotations

from typing import Callable

from core.config import MemoryConfig
from memory.store import MemoryStore, SQLiteBackend, Episode


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
        步骤 1：仅连接 DB，返回空字符串。
        步骤 4：组装两层 prefix（话题索引 + 已知事实）。
        """
        self.store.load()
        return ""

    def inject_rag_layer(self, user_input: str) -> None:
        """
        首条用户消息到达后懒加载第三层 prefix（相关历史）。
        步骤 1：空操作占位。步骤 4 实现。
        """

    def on_session_end(self) -> None:
        """
        session 结束处理：生成摘要、存储 episode、关闭 DB。
        步骤 1：仅关闭 DB。步骤 3 实现完整摘要逻辑。
        """
        self.store.close()

    # ── 对话管理（步骤 2 实现）────────────────────────────────────────────────

    def get_messages_for_llm(self) -> list:
        """步骤 2 实现：返回 BOUNDARY 切片后、过滤 ThinkTool 的消息列表。"""
        return []

    def append_message(self, message: object) -> None:
        """步骤 2 实现：追加消息到 session buffer。"""

    def maybe_compress(self) -> bool:
        """步骤 3 实现：阈值检查，按需压缩。返回是否执行了压缩。"""
        return False

    def force_compress(self) -> None:
        """步骤 3 实现：/compress 命令触发的强制压缩。"""

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
```

- [ ] **Step 4: 运行测试，确认全部通过**

```
.venv\Scripts\pytest tests/memory/ -v
```

期望：所有用例 `PASSED`

- [ ] **Step 5: 更新 `memory/__init__.py` 导出**

确认 `memory/__init__.py` 内容为（已在 Task 2 创建，此处确认无需修改）：

```python
# memory/__init__.py
from memory.manager import MemoryManager

__all__ = ["MemoryManager"]
```

- [ ] **Step 6: Commit**

```
git add memory/manager.py tests/memory/test_manager.py memory/__init__.py
git commit -m "feat(memory): add MemoryManager stub with store wiring"
```

---

## Task 7：全量测试 + 收尾

**Files:**
- Modify: `config.yaml`（补充 memory 节）

- [ ] **Step 1: 运行全量测试，确认无回归**

```
.venv\Scripts\pytest --tb=short -q
```

期望：所有既有用例 + 新增 memory 用例全部 `PASSED`，零 `FAILED`

- [ ] **Step 2: 在 `config.yaml` 补充 memory 配置节**

在 `config.yaml` 末尾追加：

```yaml
memory:
  enabled: true
  # SQLite 数据库路径（相对于本配置文件，或绝对路径）
  db_path: memory\microagent.db
  # 上下文窗口大小（token 数），与 model.n_ctx 保持一致
  context_window_tokens: 131072
  # 自动压缩阈值：context 占用超过此比例时触发（步骤 3 生效）
  compression_threshold: 0.80
  # 压缩时保留最近 N 轮对话不压缩
  keep_recent_turns: 6
  # 压缩后保留的最小空余 token 数（约 40K）
  post_compact_reserve: 40960
  # 启动时注入 prefix 的相关历史条数（0 = 完全懒加载）（步骤 4 生效）
  max_episodes_in_prefix: 5
  # 压缩摘要 prompt 中的自定义指令（留空使用默认）
  pre_compact_instructions: ""
  # 工具输出超过此字符数时 offload（步骤 3 生效）
  max_tool_output_chars: 8000
  # 少于此轮数时跳过 LLM 摘要，直接存原文（步骤 3 生效）
  min_turns_to_save: 3
  retrieval:
    bm25_weight: 0.5          # BM25 相关性权重 α（步骤 5 生效）
    recency_weight: 0.3       # 时间衰减权重 β
    importance_weight: 0.2    # 重要性权重 γ
    decay_rate: 0.1           # 时间衰减率 λ（半衰期约 7 天）
```

- [ ] **Step 3: 运行全量测试**

```
.venv\Scripts\pytest --tb=short -q
```

期望：所有用例 `PASSED`

- [ ] **Step 4: 最终 commit**

```
git add config.yaml
git commit -m "chore(config): add memory section to config.yaml"
```

---

## 验收标准

步骤 1 完成后，以下条件全部满足：

1. `pytest tests/memory/ -v` 全部通过（Episode CRUD、facts CRUD、topic_index、MemoryManager stub）
2. `pytest tests/test_config.py -v` 全部通过（含新增 MemoryConfig 测试）
3. `pytest --tb=short -q` 零失败（无回归）
4. `memory/` 目录结构完整：`__init__.py` / `store.py` / `manager.py`
5. `MemoryManager` 可实例化，`on_session_start()` / `on_session_end()` 不抛异常
6. SQLite 数据库 WAL 模式已确认（`test_sqlite_wal_mode` 通过）