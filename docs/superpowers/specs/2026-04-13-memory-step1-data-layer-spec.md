# Memory 步骤 1 — 数据层设计文档

**日期：** 2026-04-13
**范围：** `memory/` 骨架 + SQLite 持久化层 + `MemoryManager` stub
**参考：** `docs/memory-design.md` §步骤 1

---

## 目标

实现记忆系统的持久化层，使上层模块能可靠存取 episodes 和 facts，其余模块（agent、CLI）感知不到底层存储细节。本步骤不实现会话管理、压缩或检索升级，这些留给后续步骤。

---

## 文件变更清单

| 操作 | 路径 | 职责 |
|---|---|---|
| 新建 | `memory/__init__.py` | 包入口，对外只暴露 `MemoryManager` |
| 新建 | `memory/store.py` | `Episode` / `StorageBackend` ABC / `SQLiteBackend` / `MemoryStore` |
| 新建 | `memory/manager.py` | `MemoryManager` Facade stub |
| 修改 | `core/config.py` | 新增 `RetrievalConfig`、`MemoryConfig`；`AppConfig` 加 `memory` 字段 |
| 修改 | `config.yaml` | 补充 `memory:` 配置节（含注释） |
| 新建 | `tests/memory/__init__.py` | 测试包 |
| 新建 | `tests/memory/test_store.py` | `SQLiteBackend` + `MemoryStore` 单元测试 |
| 新建 | `tests/memory/test_manager.py` | `MemoryManager` stub 单元测试 |
| 修改 | `tests/test_config.py` | 新增 `MemoryConfig` 默认值断言 |

---

## 架构

### 依赖方向

```
main.py  ──►  MemoryManager  ──►  MemoryStore  ──►  StorageBackend (ABC)
                                                          ▲
                                                    SQLiteBackend (实现)

core/config.py  ──►  MemoryConfig / RetrievalConfig
core/paths.py   ──►  resolve_relative()  （调用方使用，MemoryManager 不调用）
```

依赖单向，无循环。`MemoryManager` 是唯一对外出口，外部模块不直接接触 `MemoryStore` 或 `SQLiteBackend`。

### 路径处理原则

`MemoryManager` 只接收已解析的绝对路径（由 `main.py` 调用 `core/paths.py` 的 `resolve_relative()` 完成）。`MemoryManager` 内部不做路径解析。

---

## 核心组件接口

### `Episode` dataclass

```python
@dataclass
class Episode:
    ts: str                          # ISO 8601 UTC 时间戳
    summary: str                     # 会话摘要文本
    topics: list[dict] = field(default_factory=list)
    # topics 格式：[{"name": "CUDA构建", "weight": 0.9}, ...]
    # weight 默认 1.0；步骤 3 由 LLM 生成名称，步骤 5 由算法赋权重
    id: Optional[int] = None         # DB 主键，写入前为 None
    turns: int = 0
    had_compact: bool = False
    memory_type: str = "general"     # decision|preference|milestone|problem|general
    importance: float = 0.5
```

**设计决策：** `topics` 从步骤 1 起存储为 `list[dict]`（含 weight 字段），而非 `list[str]`。权重由算法（步骤 5）而非 LLM 赋值，避免 LLM 输出浮点数不可靠的问题。步骤 1 写入时 weight 默认为 1.0。

### `StorageBackend` ABC

```python
class StorageBackend(ABC):
    @abstractmethod
    def save_episode(self, episode: Episode) -> int: ...
    @abstractmethod
    def list_episodes(self, limit: int = 50) -> list[Episode]: ...
    @abstractmethod
    def search_episodes(self, query: str, top_k: int = 5) -> list[Episode]: ...
    @abstractmethod
    def save_fact(self, key: str, value: str) -> None: ...
    @abstractmethod
    def get_all_facts(self) -> dict[str, str]: ...
    @abstractmethod
    def delete_fact(self, key: str) -> None: ...
    @abstractmethod
    def delete_episode(self, episode_id: int) -> None: ...
    @abstractmethod
    def count_episodes(self) -> int: ...
    @abstractmethod
    def close(self) -> None: ...
```

### `SQLiteBackend`

- `__init__(db_path: str)`：自动创建父目录（`mkdir parents=True`），开连接，设 WAL，执行建表 DDL
- `close()`：显式关闭连接（幂等，加 `if self._conn:` 守卫）
- `__del__`：兜底调用 `close()`，防止 GC 前连接未释放
- `topics` 列存 JSON 字符串，读取时 `json.loads` 反序列化
- `search_episodes`：本步骤退化为时间倒序（步骤 5 升级 BM25 + 时间衰减）
- `delete_episode` / `delete_fact`：不存在时静默忽略，不抛异常

### `MemoryStore`

`MemoryStore` 持有 `StorageBackend`，暴露业务语义接口：

- `save_episode(summary, topics, turns, had_compact, memory_type, importance)`：内部生成 `ts`，不要求调用方传时间戳
- `retrieve_episodes(query, top_k)` → `list[Episode]`
- `get_topic_index(limit) -> dict[str, float]`：聚合所有 episodes 的 topics，**按 weight 累加**降序返回 top N
- `set_fact / get_all_facts / delete_fact / delete_episode / count_episodes`：直接代理 Backend
- `load()` / `close()`：生命周期钩子，`close()` 调用 `backend.close()`

### `MemoryManager` stub

```python
class MemoryManager:
    def __init__(self, config: MemoryConfig, token_counter: Callable[[list], int])
    def on_session_start(self) -> str        # 调用 store.load()，返回 ""
    def inject_rag_layer(self, user_input: str) -> None   # 空操作，步骤 4
    def on_session_end(self) -> None         # 调用 store.close()
    def get_messages_for_llm(self) -> list   # WARNING + 返回 []，步骤 2
    def append_message(self, message) -> None  # WARNING + 空操作，步骤 2
    def maybe_compress(self) -> bool         # WARNING + 返回 False，步骤 3
    def force_compress(self) -> None         # WARNING + 空操作，步骤 3
    def set_fact / delete_fact / get_facts   # 代理 store
    def retrieve_episodes / delete_episode / episode_count  # 代理 store
    # 公开属性
    store: MemoryStore
    context: None  # 步骤 2 接入 ContextManager
```

**stub 行为：** 未实现方法打印 `log.warning("MemoryManager.<method> not yet implemented (Step N)")` 后返回空值，不抛异常。

---

## 数据库 Schema

```sql
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
```

WAL 模式：`PRAGMA journal_mode=WAL`（启动时设置）。

---

## `MemoryConfig` / `RetrievalConfig`

```python
class RetrievalConfig(BaseModel):
    bm25_weight: float = 0.5
    recency_weight: float = 0.3
    importance_weight: float = 0.2
    decay_rate: float = 0.1

class MemoryConfig(BaseModel):
    enabled: bool = True
    db_path: str = r"memory\microagent.db"   # 调用方负责解析为绝对路径
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

---

## 错误处理

| 场景 | 处理 |
|---|---|
| `db_path` 父目录不存在 | `SQLiteBackend.__init__` 自动 `mkdir(parents=True, exist_ok=True)` |
| SQLite 操作异常（磁盘满、权限等） | 不捕获，向上抛出 |
| `delete_episode` / `delete_fact` id/key 不存在 | 静默忽略 |
| stub 方法被调用 | `log.warning(...)` 后返回空值，不抛异常 |
| `SQLiteBackend.close()` 多次调用 | `if self._conn:` 守卫，幂等 |

---

## 测试策略

严格 TDD：每个实现单元先写失败测试，再写最小实现。

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/test_config.py`（追加） | `MemoryConfig` 默认值、YAML 覆盖、`RetrievalConfig` 字段 |
| `tests/memory/test_store.py` | `Episode` 字段和默认值；`StorageBackend` 不可实例化；`SQLiteBackend` CRUD（增删查、排序、limit、upsert）、WAL mode（PRAGMA 验证）；`MemoryStore` 业务方法（含 `get_topic_index` 加权聚合） |
| `tests/memory/test_manager.py` | 实例化；`on_session_start` 返回字符串；`on_session_end` 不抛异常；facts CRUD；`episode_count`；stub 方法打印 WARNING 不抛异常 |

全量回归：每个 Task commit 前跑 `pytest --tb=short -q`，零失败。

---

## 验收标准

1. `pytest tests/memory/ -v` 全部通过
2. `pytest tests/test_config.py -v` 全部通过（含新增 MemoryConfig 测试）
3. `pytest --tb=short -q` 零失败（无回归）
4. `memory/` 目录结构完整：`__init__.py` / `store.py` / `manager.py`
5. `MemoryManager` 可实例化，`on_session_start()` / `on_session_end()` 不抛异常
6. `PRAGMA journal_mode` 返回 `wal`（`test_sqlite_wal_mode` 通过）
