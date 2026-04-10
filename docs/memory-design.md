# 记忆与上下文系统设计文档

> 状态：设计探讨阶段（未实现）
> 最后更新：2026-04-10
> 参考：Claude Code 源码架构分析、ZeroClaw 架构分析（docs/references/）

---

## 设计原则

1. **轻量**：存储用 Python 内置 `sqlite3`，零额外依赖；`rank-bm25` 为唯一外部依赖
2. **易用性优先**：代码复杂度可以换来更低 token 消耗、更好的模型表现、更少内存占用
3. **五脏俱全**：功能可简单，接口必须完整；stub 实现要有注释说明扩展方向

---

## 模型上下文

- **模型**：Gemma-4 E2B Instruct（GGUF）
- **上下文窗口**：128K tokens（`context_window_tokens: 131072`）
- **Token 计数**：使用 llama-cpp-python 自带的 `llama.tokenize()`，对 Gemma tokenizer 最准确，零新增依赖

---

## 核心拆分原则

记忆与上下文管理沿**"是否跨 session 存活"**这条线分离：

| | 记忆（Memory） | 上下文（Context） |
|---|---|---|
| **生命周期** | 跨 session，持久化 | 随 session，内存态 |
| **存储介质** | SQLite | Python list（in-memory） |
| **核心问题** | 什么值得记？怎么找回？ | LLM 该看到什么？窗口够不够？ |
| **演化方向** | 检索算法、云同步、加密 | 压缩策略、多模态、注入格式 |

依赖方向：`ContextManager → MemoryStore`（单向，无循环）

---

## 系统架构

```
cli/app.py
    │
    ▼
MemoryManager（Facade）
    ├── ContextManager          # 纯 session 管理，无持久化
    │       ├── session buffer（含 BOUNDARY 标记）
    │       ├── token 计数 + 压缩触发
    │       └── ──────────────────────────────────────┐
    │                                                  │ 读：加载前缀
    └── MemoryStore             # 纯持久化，无 session 感知
            ├── SQLiteBackend                          │ 写：保存摘要/事实
            ├── episodes 表 ◄──────────────────────────┘
            ├── facts 表
            └── Retrieval（BM25 + 时间衰减）
```

---

## 记忆感知（Memory Awareness）

### 核心问题

LLM 默认不知道数据库里有什么。若只给它一个 `memory_recall` 工具但不告诉它"有关于 CUDA 的记忆"，它就不知道该不该去查，大概率直接回答"我不记得了"。

**行业主流方案对比**：

| 方案 | 做法 | 问题 |
|------|------|------|
| 全量注入 | 每次把所有记忆塞进 context | 记忆一多就撑爆 context |
| RAG 预检索 | 用 query 搜出 top-K 自动注入 | LLM 无法主动要求检索更多 |
| 纯工具驱动 | 只给工具，不注入任何内容 | LLM 不知道有什么，无从触发 |
| **轻量索引 + 工具（采用）** | 注入极小的话题目录 + 按需工具检索 | — |

### 我们的方案：三层 Context Prefix（两层即时 + 一层懒加载）

session 开始时注入前两层（话题索引 + 已知事实），总量通常 < 150 token；
第三层（相关历史）在首条用户消息到达后懒加载注入，合计 < 300 token：

```
[记忆]
## 话题索引
CUDA构建(3) · CI调试(2) · 项目架构(5) · 用户偏好(已知)
如需检索具体内容，调用 memory_recall 工具。

## 已知事实
- language: zh
- model_path: models/gemma4.gguf
- user_name: Pheobe

## 相关历史（自动检索）
- [2026-04-10] CUDA CI 构建调试：method:local 解决了 0xE0E00019 错误
- [2026-04-09] 项目初始化，确定三种构建变体（cuda/vulkan/cpu）
[/记忆]
```

三层的分工：

| 层 | 内容 | 作用 | token 量 |
|---|---|---|---|
| **话题索引** | 所有 episode topics 聚合计数 | 让 LLM 知道"有什么"，触发主动检索 | 极小（~50） |
| **已知事实** | facts 表全量 | 直接可用，无需工具调用 | 小（~100） |
| **相关历史** | RAG 预检索 top-K 摘要 | 猜测最相关的先注入（懒加载，首条消息触发） | 中（~150/条） |

### 话题索引的生成

从 episodes 表聚合所有 topics，按出现频次排序：

```sql
-- topics 字段存储 JSON 数组，需解析后聚合
-- 全量扫描所有 episodes（通常 < 1000 条，Python Counter 足够快）
-- limit 参数控制返回的 topic 数量（非扫描行数），按频次降序截断
SELECT topics FROM episodes
-- Python: Counter(topic for ep in rows for topic in json.loads(ep.topics))
```

输出格式：`CUDA构建(3) · CI调试(2) · 项目架构(5)`（按频次降序，截断超过 10 个话题）

### 注入时机与刷新

- **session 开始**：生成前两层 prefix（话题索引 + 已知事实），作为 system prompt 的一部分
- **首条用户消息到达**：调用 `inject_rag_layer(user_input)` 懒加载第三层（相关历史），追加到 prefix（一次性，之后不再刷新）
- **session 内**：prefix 不刷新（避免干扰 smolagents 的消息历史）
- **压缩时**：BOUNDARY 消息中不包含 prefix（prefix 只在 system prompt 层，不在对话消息里）
- **懒加载模式**：设 `max_episodes_in_prefix: 0` 可跳过第三层（相关历史），只注入话题索引和事实，完全依赖 `MemoryRecallTool` 按需检索（更省 token，适合 context 紧张场景）

---

## ⚗️ 内联记忆标注（实验性）

> **状态**：实验性设计，尚未实现。核心机制有潜力，但效果高度依赖 topic 质量。

### 灵感来源

维基百科中的蓝色超链接：读者无需主动搜索，文中的专有名词本身就在告诉你"这里有更多细节可以查"。对应到记忆系统：**在用户输入到达 LLM 之前，把命中记忆的词组标注出来**，让 LLM 不需要"想到"该不该查，而是直接"看到"提示。

```
用户原始输入：
  "帮我修复整个CUDA构建报错"

标注后传给 LLM：
  "帮我修复整个 [CUDA源码编译 ↗5条: 3问题 2决策] 报错"
```

LLM 看到 `[... ↗N条: 类型]` 格式，结合 system prompt 中的说明，知道可以调用 `memory_recall` 获取详情。

### 核心挑战：topic 质量

标注系统的上限完全取决于 topic 的质量，topic 需要满足一对看似矛盾的要求：

| | 过于具体 | 理想区间 | 过于宽泛 |
|---|---|---|---|
| **示例** | "0xE0E00019退出码" | "CUDA CI构建失败" | "错误" |
| **辨识度** | ✅ 高 | ✅ 高 | ❌ 低 |
| **可召回性** | ❌ 用户不会复述 | ✅ 自然语言能匹配 | ✅ 但噪声大 |

**理想 topic**：4-12 字，能概括"这段记忆讲的是什么事"，而不是"出现了什么词"。

### 方案一：LLM 结构化生成（推荐）

在生成 episode 摘要时，合并输出 topic，**零额外模型调用**：

```python
SUMMARY_PROMPT = """
分析以下对话，输出 JSON（不要其他内容）：
{
  "summary": "2-3句话的摘要",
  "topics": ["词组1", "词组2"],
  "type": "decision|milestone|problem|preference|general"
}

topic 要求：
- 数量：3-5个，每个 3-15 字
- 具体：不要"错误"，要"CUDA CI构建失败"
- 可召回：用户将来用自然语言提问时应能匹配

好的示例：["CUDA源码编译", "Jimver/cuda-toolkit CI配置", "Windows Server 2025兼容性"]
差的示例：["CUDA", "错误", "Python", "构建问题"]
"""
```

### 方案二：词频统计（零额外调用，精度较低）

从 session buffer 中提取高频 n-gram，过滤停用词，取 top-K。适合作为 LLM 方案的降级兜底。

### 匹配策略：词组重叠（非精确子串）

用户说"CUDA构建报错"，存储的 topic 是"CUDA源码编译"——两者不完全相同，精确子串匹配会漏掉。改用**字符重叠率**：

```python
def overlap_score(text: str, topic: str) -> float:
    """中文用字符集交集，英文用词集交集"""
    t_chars = set(topic.replace(" ", ""))
    s_chars = set(text.replace(" ", ""))
    return len(t_chars & s_chars) / len(t_chars)

def annotate_user_input(text: str, topic_index: dict[str, int],
                         episode_type_dist: dict[str, dict],
                         threshold: float = 0.6) -> str:
    """
    对用户输入进行内联记忆标注。
    
    未来扩展方向：
    - 语义相似度替代字符重叠（需要嵌入模型）
    - 实体识别联动 facts 表（人名、项目名）
    - 动态阈值（根据 topic 的 IDF 值调整）
    """
    # 按 topic 长度降序，避免短词覆盖长词
    sorted_topics = sorted(topic_index, key=len, reverse=True)
    for topic in sorted_topics:
        if overlap_score(text, topic) >= threshold:
            n = topic_index[topic]
            dist = episode_type_dist.get(topic, {})
            dist_str = " ".join(f"{v}{k}" for k, v in dist.items() if v)
            annotation = f"[{topic} ↗{n}条: {dist_str}]"
            # 只标注第一个高重叠区域，避免过度标注
            text = text.replace(
                _find_best_match(text, topic), annotation, 1
            )
    return text
```

### IDF 过滤：自动剔除低辨识度 topic

随着 episodes 积累，出现在大多数会话中的 topic 辨识度趋近于零：

```python
def topic_idf(topic: str, all_episodes: list[Episode]) -> float:
    """topic 的逆文档频率，值越高辨识度越强"""
    n_total = len(all_episodes)
    n_match = sum(1 for ep in all_episodes if topic in ep.topics)
    if n_match == 0:
        return 0.0
    return math.log(n_total / n_match)

# 标注时只使用 IDF > 阈值的 topic（默认 0.5）
# "Python" 出现在 80% episode → IDF ≈ 0.22 → 不标注
# "CUDA CI构建失败" 只出现 1 次 → IDF 高 → 强标注
```

### 完整链路

```
会话结束时：
  LLM 同步生成 { summary, topics, type }（一次调用）
  → IDF 计算，过滤高频低辨识度 topic
  → 存入 episodes 表（topics 字段）

用户下次输入："帮我修复整个CUDA构建报错"
  → annotate_user_input()
      字符重叠匹配 topic_index
      命中 "CUDA源码编译"（score=0.75）
      命中 "CI构建失败"（score=0.80）
  → 标注后消息：
      "帮我修复整个 [CUDA源码编译 ↗5条: 3问题 2决策] 报错"
  → LLM 看到标注，调用 memory_recall("CUDA源码编译")
  → 拿回过去踩坑经历，精准回答
```

### 在架构中的位置

属于 `ContextManager` 的预处理步骤，在每轮用户消息传入时调用：

```python
class ContextManager:
    def annotate_user_input(self, text: str) -> str:
        """
        [实验性] 内联记忆标注。
        在 append_message() 前调用，标注结果作为传给 LLM 的实际消息内容。
        可通过 config 的 memory.inline_annotation: false 关闭。
        """
```

System prompt 中需添加格式说明（约 30 token）：

```
消息中 [词语 ↗N条: 类型分布] 表示记忆库有 N 条相关历史。
需要详情时调用 memory_recall 工具。
```

### 配置项

```yaml
memory:
  inline_annotation: true          # 是否启用内联标注（实验性，默认开启）
  annotation_threshold: 0.6        # 词组重叠率阈值
  annotation_idf_min: 0.5          # topic 最低 IDF，低于此值不标注
  annotation_max_per_message: 5    # 单条消息最多标注数量，避免过度噪声
```

---

## MemoryStore — 持久化层

### 职责

- 读写 SQLite（episodes / facts 两张表）
- BM25 + 时间衰减混合检索
- `StorageBackend` 抽象，支持未来换实现

### 数据库 Schema

```sql
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,              -- ISO 8601 时间戳
    summary     TEXT    NOT NULL,              -- 会话摘要
    topics      TEXT    NOT NULL DEFAULT '[]', -- JSON 数组，关键词
    turns       INTEGER NOT NULL DEFAULT 0,
    had_compact INTEGER NOT NULL DEFAULT 0,    -- 是否触发过压缩
    memory_type TEXT    NOT NULL DEFAULT 'general',
    -- 参考 mempalace：decision | preference | milestone | problem | general
    -- 由 regex 标记自动分类（无需 LLM），存储时写入，检索时加权
    importance  REAL    NOT NULL DEFAULT 0.5
    -- 参考 mempalace drawer weight：0.0-1.0
    -- 简单规则打分：decision/milestone +0.3，had_compact +0.1，turns>20 +0.1
);

CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 预留：未来多 Agent 任务系统
-- CREATE TABLE IF NOT EXISTS tasks (...);
```

### StorageBackend 抽象

```python
class StorageBackend(ABC):
    def save_episode(self, episode: Episode) -> None: ...
    def list_episodes(self, limit: int = 50) -> list[Episode]: ...
    def search_episodes(self, query: str, top_k: int) -> list[Episode]: ...
    def save_fact(self, key: str, value: str) -> None: ...
    def get_all_facts(self) -> dict[str, str]: ...
    def delete_fact(self, key: str) -> None: ...
    def delete_episode(self, episode_id: int) -> None: ...
    def count_episodes(self) -> int: ...

class SQLiteBackend(StorageBackend):
    """
    主实现。WAL 模式支持并发读，事务保证原子写。
    未来可替换为：加密 SQLite（SQLCipher）、远程 DB、云同步后端。
    """
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
```

### MemoryStore 接口

```python
class MemoryStore:
    def load(self) -> None: ...                                    # 连接 DB，预热缓存
    def close(self) -> None: ...                                   # 关闭连接

    # Episodes
    def save_episode(self, summary: str, topics: list[str], turns: int,
                     had_compact: bool, memory_type: str,
                     importance: float) -> None: ...
    def retrieve_episodes(self, query: str, top_k: int) -> list[Episode]: ...
    def get_topic_index(self, limit: int = 10) -> dict[str, int]: ...
    # 返回 {"CUDA构建": 3, "项目架构": 5, ...}，按频次降序，用于生成话题索引

    # Facts
    def get_all_facts(self) -> dict[str, str]: ...
    def set_fact(self, key: str, value: str) -> None: ...
    def delete_fact(self, key: str) -> None: ...

    # Metadata
    def count_episodes(self) -> int: ...
```

### Retrieval — 混合检索

参考 ZeroClaw 的混合检索设计和 mempalace 的重要性权重，采用三维加权评分：

```
score(episode, query) = α × normalize(bm25(episode.summary, query))
                      + β × exp(-λ × days_since(episode.ts))
                      + γ × episode.importance

默认值：α=0.5, β=0.3, γ=0.2, λ=0.1（时间半衰期约 7 天）
```

**importance 打分规则**（存储时计算，无需 LLM）：

```python
def calc_importance(summary: str, memory_type: str,
                    turns: int, had_compact: bool) -> float:
    score = 0.5
    if memory_type in ("decision", "milestone"): score += 0.3
    if memory_type == "problem":                 score += 0.1
    if had_compact:                              score += 0.1
    if turns > 20:                               score += 0.1
    return min(score, 1.0)
```

**memory_type 自动分类**（regex 标记，无需 LLM，参考 mempalace）：

```python
MEMORY_TYPE_MARKERS = {
    "decision":   ["决定", "采用", "选择", "we decided", "let's use", "trade-off"],
    "preference": ["总是", "永远不", "偏好", "always use", "never do", "prefer"],
    "milestone":  ["完成", "成功", "发布", "shipped", "working", "achieved"],
    "problem":    ["报错", "失败", "bug", "error", "failed", "issue"],
}

def detect_memory_type(summary: str) -> str:
    for type_name, markers in MEMORY_TYPE_MARKERS.items():
        if any(m in summary.lower() for m in markers):
            return type_name
    return "general"
```

**实现路径**：
1. **当前**：按时间倒序返回最近 N 条（零依赖）
2. **下一步**：引入 `rank-bm25`，加入 importance 维度
3. **再下一步**：加入时间衰减，完整三维评分

**未来方向**（接口不变，替换实现）：
- 本地嵌入模型 + 余弦相似度（精度更高，适合大量 episodes）
- ⚠️ ChromaDB 因 ONNX 依赖与 Nuitka 不兼容，排除

---

## ContextManager — Session 管理层

### 职责

- 维护 session 消息列表（含 BOUNDARY 标记）
- Token 计数，驱动压缩决策
- 三种压缩触发方式
- 启动时从 MemoryStore 加载记忆前缀
- Session 结束时将摘要交给 MemoryStore 存储

### Session Buffer

```python
# 消息类型标记
MSG_NORMAL   = "normal"
MSG_BOUNDARY = "boundary"   # 压缩边界，内含摘要文本
MSG_THINK    = "think"      # ThinkTool 输出，不传给 LLM（压缩摘要时另行包含）

# 发给 LLM 时只取最后一个 BOUNDARY 之后的消息，并过滤 ThinkTool 输出
def get_messages_for_llm(buffer: list[Message]) -> list[Message]:
    # 步骤 1：取 BOUNDARY 之后的切片（BOUNDARY 本身作为摘要消息保留）
    for i in reversed(range(len(buffer))):
        if buffer[i].type == MSG_BOUNDARY:
            boundary_slice = buffer[i:]
            break
    else:
        boundary_slice = buffer
    # 步骤 2：过滤 ThinkTool 输出（节省 token；压缩摘要时会单独包含 think 内容）
    return [m for m in boundary_slice if m.type != MSG_THINK]
```

### 压缩策略

**触发方式**：
- **自动**：每轮结束后 `token_count(messages_for_llm) / context_window >= threshold`
- **手动**：CLI `/compress` 命令
- **响应式（兜底）**：捕获 llama-cpp-python 上下文溢出异常，`has_attempted_reactive_compact` flag 防无限循环

**压缩算法（Sliding Window + Boundary Marker）**：

```
压缩前（发给 LLM 的部分）：
  [旧摘要?, T_n-8, T_n-7, ..., T_n-1, T_n]

压缩后（插入 BOUNDARY，保留最近 keep_recent_turns 轮）：
  [BOUNDARY: "之前讨论了...", T_n-5, T_n-4, T_n-3, T_n-2, T_n-1, T_n]
```

压缩后设置 `post_compact_reserve` 保留量，防止立即再次触发。

**ThinkTool 输出的处理**：
- **排除**在发给 LLM 的边界后消息之外（减少 token）
- **包含**在生成压缩摘要的输入中（让摘要理解推理脉络）

**Pre-Compress 指令注入**：

压缩前在摘要 prompt 中注入 `pre_compact_instructions`（config 字段）：
```
"摘要时始终保留：文件路径、工具调用结果、用户明确说明的约束条件"
```

### Token Budget 追踪

```python
@dataclass
class TokenBudget:
    context_window: int
    used_in_current_context: int    # 边界之后的 token 数（影响压缩决策）
    total_consumed_session: int     # 本次 session 累计消耗（含已压缩部分）
    compact_count: int              # 本次 session 压缩次数
```

### ContextManager 接口

```python
class ContextManager:
    def __init__(self, store: MemoryStore, config: MemoryConfig,
                 token_counter: Callable[[list], int]): ...
    # token_counter：注入自 LlamaCppBackend 的 tokenize 封装
    # 签名：fn(messages: list[Message]) -> int，返回估算 token 总数
    # 由 MemoryManager 在构建时从外部传入，ContextManager 不直接依赖 llama-cpp-python

    def start_session(self) -> str:
        """
        组装两层 context_prefix 注入 system prompt：
          1. 话题索引（store.get_topic_index()）
          2. 已知事实（store.get_all_facts()）
        第三层（相关历史）在首条用户消息后通过 inject_rag_layer() 懒加载。
        返回格式化后的 prefix 字符串。
        """

    def inject_rag_layer(self, user_input: str) -> None:
        """
        首条用户消息到达后调用，补充第三层（相关历史）到 prefix。
        只执行一次（内部 has_injected_rag 标志防止重复注入）。
        若 max_episodes_in_prefix == 0，直接跳过。
        """

    def end_session(self) -> None:
        """
        session 结束处理：
        - turns >= min_turns_to_save：调用 LLM 生成 { summary, topics, type }
          → store.save_episode(summary, topics, turns, had_compact, memory_type, importance)
        - turns < min_turns_to_save：跳过 LLM，将最后 N 轮原文拼接为 summary 直接存储
        - LLM 失败兜底：截取最后 keep_recent_turns 轮原文为 summary，
          topics=[]，memory_type="general"，importance=0.3，
          打印 ERROR 到 ui/console.py 的共享 console，仍执行 save_episode
        """

    def get_messages_for_llm(self) -> list: ...
    def append_message(self, message: Message) -> None: ...

    def maybe_compress(self) -> bool: ...      # 阈值检查，按需压缩
    def force_compress(self) -> None: ...      # /compress 命令
    def reactive_compress(self) -> bool: ...   # 溢出兜底

    def token_usage(self) -> TokenBudget: ...
```

---

## MemoryManager — Facade 层

对 `cli/app.py` 和 `core/agent.py` 暴露统一接口，屏蔽内部拆分细节：

```python
class MemoryManager:
    """
    协调 MemoryStore 和 ContextManager。
    调用方无需感知两者的存在，只与 MemoryManager 交互。
    """
    def __init__(self, config: MemoryConfig, token_counter: Callable[[list], int]):
        self.store   = MemoryStore(SQLiteBackend(config.db_path))
        self.context = ContextManager(self.store, config, token_counter)

    # 生命周期
    def on_session_start(self) -> str: ...             # 返回两层 context_prefix
    def inject_rag_layer(self, user_input: str) -> None: ...  # 首条消息后懒加载第三层
    def on_session_end(self) -> None: ...

    # 对话管理
    def get_messages_for_llm(self) -> list: ...
    def append_message(self, message: Message) -> None: ...
    def maybe_compress(self) -> bool: ...
    def force_compress(self) -> None: ...

    # 事实管理（CLI 命令 + MemoryStoreTool 调用入口）
    def set_fact(self, key: str, value: str) -> None: ...
    def delete_fact(self, key: str) -> None: ...
    def get_facts(self) -> dict[str, str]: ...

    # Episode 管理（MemoryRecallTool / MemoryForgetTool 调用入口）
    def retrieve_episodes(self, query: str, top_k: int = 5) -> list[Episode]: ...
    def delete_episode(self, episode_id: int) -> None: ...

    # 状态查询（/memory 命令用）
    def token_usage(self) -> TokenBudget: ...
    def episode_count(self) -> int: ...
```

---

## 记忆管理工具（Memory Tools）

参考 ZeroClaw 的 `recall / store / forget` 工具，让模型主动操作 MemoryStore：

```python
class MemoryStoreTool(MicroTool):
    """模型主动将对话中的事实存入 facts 表"""
    name = "memory_store"
    is_read_only = False

class MemoryRecallTool(MicroTool):
    """模型主动检索历史 episodes（混合检索），回答跨会话问题"""
    name = "memory_recall"
    is_read_only = True

class MemoryForgetTool(MicroTool):
    """删除指定 fact 或 episode，is_destructive=True 走确认流程"""
    name = "memory_forget"
    is_read_only = False
    is_destructive = True
```

三个工具通过 **MemoryManager Facade** 操作记忆（不经过 ContextManager）。MemoryManager 已为此暴露 `retrieve_episodes`、`delete_episode`、`set_fact`、`delete_fact` 等方法，工具不持有 MemoryStore 的直接引用，保持 Facade 封装一致性。

---

## 模块结构

```
memory/
├── __init__.py
├── manager.py      # MemoryManager（Facade）：对外统一接口
├── store.py        # MemoryStore + StorageBackend ABC + SQLiteBackend
├── context.py      # ContextManager：session buffer、压缩、token 计数
└── retrieval.py    # 检索逻辑（BM25 + 时间衰减），被 MemoryStore 调用
```

---

## 完整会话流程

```
启动时（并行）：
  后台：manager.on_session_start()
    → store.load()（连接 SQLite）
    → store.get_topic_index()         → 话题索引（层 1）
    → store.get_all_facts()           → 已知事实（层 2）
    → 组装 context_prefix（两层，< 150 token；启动时无用户输入，跳过第三层）
  前台：加载模型、打印 banner

第一轮：
  首条用户消息到达：
    → [实验性] manager.annotate_user_input(user_input)（内联标注）
    → manager.inject_rag_layer(user_input)（懒加载第三层，追加到 prefix，一次性）
  agent.run(system_prompt + context_prefix + user_prompt, reset=True)
  manager.append_message(user_msg)
  manager.append_message(assistant_msg)

后续每轮：
  → [实验性] manager.annotate_user_input(user_input)（内联标注）
  agent.run(manager.get_messages_for_llm(), reset=False)
  → manager.maybe_compress()（阈值检查）
  → 捕获 context_overflow → manager.reactive_compress()（兜底）

/compress 命令：
  manager.force_compress()

退出时：
  manager.on_session_end()
    → context → 生成/复用摘要
    → store.save_episode(...)
    → store 关闭连接
```

---

## 配置参数（计划加入 config.yaml）

```yaml
memory:
  enabled: true
  db_path: memory\microagent.db    # 相对于 config.yaml；主目录为 ~\.pheobe\MicroAgent\memory\
  context_window_tokens: 131072     # Gemma-4 E2B 上下文大小
  compression_threshold: 0.80       # 自动压缩阈值（占 context 的比例）
  keep_recent_turns: 6              # 压缩时保留最近 N 轮不动
  post_compact_reserve: 40960       # 压缩后必须保留的空余 token（~40K）
  max_episodes_in_prefix: 5         # 启动时注入的相关历史条数；0 = 完全懒加载
  pre_compact_instructions: ""      # 压缩摘要 prompt 中注入的自定义指令
  max_tool_output_chars: 8000       # 工具输出超出此值时 offload 到临时文件
  min_turns_to_save: 3              # 少于此轮数时跳过 LLM 压缩，直接存原文（防止短会话浪费调用）
  retrieval:
    bm25_weight: 0.5                # BM25 相关性权重 α
    recency_weight: 0.3             # 时间衰减权重 β
    importance_weight: 0.2          # 重要性权重 γ（参考 mempalace）
    decay_rate: 0.1                 # 时间衰减率 λ（半衰期约 7 天）
```

---

## CLI 命令（计划）

| 命令 | 功能 |
|------|------|
| `/compress` | 立即手动压缩当前会话，展示本次摘要 |
| `/memory` | 查看状态：token 占用、episode 条数、已知事实列表 |
| `/memory set <key> <value>` | 手动更新 fact |
| `/memory forget <key>` | 删除指定 fact |

---

## 待决策

- [x] `db_path` 全局路径：已确定使用 `~\.pheobe\MicroAgent\memory\microagent.db`，config.yaml 中路径相对于 config.yaml 自身位置（见 engineering-design.md §7）
- [ ] 工具输出 offload 的内容写入 SQLite 便于检索，还是纯临时文件？
- [ ] 三个 Memory Tools 默认是否启用，还是在 config 中显式开启？
- [ ] `pre_compact_instructions` 是否允许运行时通过命令修改？

---

## 开发路线图

按"能独立运行、能独立测试"切分，每步完成后有可验证的交付物。前四步为必须实现的核心功能，后三步为质量提升与扩展。

### 步骤 0 — 项目部署结构：config 查找与目录初始化

**修改文件**：`core/config.py`、`main.py`、`ui/logger.py`

- `find_config() -> Path`：按优先级查找配置文件
  1. `~\.pheobe\MicroAgent\config.yaml`
  2. `<exe所在目录>\config.yaml`
  3. 都不存在 → 调用 `bootstrap_user_dir()`，生成默认配置并提示用户
- `bootstrap_user_dir()`：创建完整用户目录树（`models/memory/logs/skills`）；若 exe 同级有 `config.yaml` 则复制，否则写入内置默认模板
- 确认 config.yaml 中所有路径均相对于 config.yaml 自身位置解析（`core/config.py` 已有此逻辑，规范化即可）
- 日志路径迁移至 `~\.pheobe\MicroAgent\logs\microagent-YYYY-MM-DD.log`

**交付物**：程序从正确位置加载配置，用户目录结构首次运行自动初始化，日志写入正确路径。

---

### 步骤 1 — 数据层：`memory/` 骨架 + SQLite

**新增文件**：`memory/__init__.py`、`memory/store.py`

- `StorageBackend` ABC（`save_episode / list_episodes / search_episodes / save_fact / get_all_facts / delete_fact / delete_episode / count_episodes`）
- `SQLiteBackend`：WAL 模式，建表，基础 CRUD
- `MemoryStore`：包装 Backend，暴露业务接口
- `MemoryManager` stub（空实现，接口占位）
- `core/config.py` 新增 `MemoryConfig` 节
- 单元测试：增删改查、WAL 并发读

**交付物**：数据库能存取 episodes 和 facts，其余模块感知不到。

---

### 步骤 2 — Session 管理：`ContextManager` + token 计数

**新增文件**：`memory/context.py`

- `MSG_NORMAL / MSG_BOUNDARY / MSG_THINK` 类型系统
- session buffer（`list[Message]`）
- `get_messages_for_llm()`：BOUNDARY 切片 + ThinkTool 过滤（两步）
- `token_counter: Callable[[list], int]` 注入，`TokenBudget` dataclass
- `MemoryManager` 接入 `ContextManager`，`get_messages_for_llm()` / `append_message()` 代理
- `core/agent.py` 和 `cli/app.py` 改用 `manager.get_messages_for_llm()` / `manager.append_message()`

**交付物**：Agent 通过新 context 管理跑起来，`/memory` 可显示 token 占用（即使记忆尚未持久化）。

---

### 步骤 3 — 压缩三机制

**修改文件**：`memory/context.py`、`cli/app.py`

- `maybe_compress()`：阈值检查（`token_used / context_window >= compression_threshold`）
- `force_compress()`：`/compress` 手动命令
- `reactive_compress()`：捕获 llama-cpp-python 上下文溢出异常，`has_attempted_reactive_compact` flag 防循环
- `end_session()`：
  - `turns >= min_turns_to_save` → 调 LLM 生成 `{ summary, topics, type }` → `store.save_episode()`
  - `turns < min_turns_to_save` → 原文拼接直接存储
  - LLM 失败兜底 → 截取最后 `keep_recent_turns` 轮，`importance=0.3`，打印 ERROR
- `pre_compact_instructions` 注入压缩 prompt
- `cli/app.py` 注册 `/compress` 命令

**交付物**：长对话可以自动/手动压缩，session 历史持久化进数据库。

---

### 步骤 4 — 记忆注入：context prefix + facts 管理

**修改文件**：`memory/context.py`、`memory/manager.py`、`cli/app.py`

- `start_session()`：两层 prefix（`get_topic_index()` + `get_all_facts()`）
- `inject_rag_layer(user_input)`：首条消息懒加载第三层（时序简单检索，BM25 留到步骤 5）
- `MemoryManager` 暴露 `set_fact / delete_fact / get_facts`
- `cli/app.py` 注册 `/memory`、`/memory set`、`/memory forget` 命令

**交付物**：模型启动时能看到历史话题和已知事实；用户可通过命令管理 facts。

---

### 步骤 5 — 检索升级：BM25 + 重要性评分

**新增文件**：`memory/retrieval.py`

- 引入 `rank-bm25`（懒加载：`from rank_bm25 import BM25Okapi`）
- `detect_memory_type(summary)`：regex 分类
- `calc_importance(summary, memory_type, turns, had_compact)`：规则打分
- 三维加权评分：`α×BM25 + β×exp(-λ×days) + γ×importance`
- `MemoryStore.retrieve_episodes()` 切换到混合检索
- `save_episode()` 存储时自动计算 `memory_type` 和 `importance`

**交付物**：RAG 第三层检索质量显著提升，相关历史更准确地注入 prefix。

---

### 步骤 6 — Memory Tools：让模型主动操记忆

**新增文件**：`tools/memory_tools.py`

- `MemoryStoreTool`：调用 `manager.set_fact()`
- `MemoryRecallTool`：调用 `manager.retrieve_episodes()`
- `MemoryForgetTool`：调用 `manager.delete_fact()` / `manager.delete_episode()`，`is_destructive=True`
- 注册到 `tools/registry.py`，`config.yaml` 新增 `tools.memory` 开关

**交付物**：模型可以在对话中主动查历史、存事实、删记忆，不依赖用户手动命令。

---

### 步骤 7 — 内联标注（实验性）

**修改文件**：`memory/context.py`

- `SUMMARY_PROMPT` 结构化输出：合并生成 `{ summary, topics, type }`，零额外模型调用
- `overlap_score(text, topic)`：字符集交集匹配
- `topic_idf(topic, all_episodes)`：IDF 过滤低辨识度 topic
- `annotate_user_input(text)`：标注命中 topic，格式 `[topic ↗N条: 类型]`
- `config.yaml` 新增 `inline_annotation` 开关（默认开启，可随时关闭）

**交付物**：用户输入命中历史 topic 时自动标注，LLM 主动召回率提升（实验性，效果依赖 topic 质量）。

