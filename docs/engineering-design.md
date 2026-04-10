# 工程设计参考文档

> 状态：设计参考（部分已实现，部分待实现）
> 最后更新：2026-04-10
> 参考来源：Claude Code 源码架构分析、ZeroClaw 架构分析（docs/references/）

本文记录对 MicroAgent 整体工程有参考价值的设计模式，按关注点分区，与具体功能实现文档（如 memory-design.md）分开维护。

---

## 一、工具系统（Tool System）

### 1.1 工具接口扩展

当前 `MicroTool` 只有 `name / description / inputs / output_type / forward()`。参考 Claude Code 的 Tool 接口，应扩展以下属性：

```python
class MicroTool(Tool):
    # 已有字段
    name: str
    description: str
    inputs: dict
    output_type: str

    # 新增：工具属性声明（影响调度与权限）
    is_read_only: bool = True          # 只读工具可并发执行；写入工具串行
    is_destructive: bool = False       # 不可逆操作（删除、覆盖）需额外确认
    interrupt_behavior: str = "cancel" # 用户 Ctrl+C 时的行为：'cancel' 或 'block'
    max_output_chars: int = 8000       # 输出超出此值时 offload 到临时文件

    # 别名支持（向后兼容工具名变更）
    aliases: list[str] = []
```

`is_read_only` 和 `is_destructive` 都影响权限链路，也是未来并发调度的基础。即使当前串行执行，先声明好接口，未来无需改工具代码。

### 1.2 工具注册：三函数模式

参考 Claude Code 的 `getAllBaseTools / getTools / assembleToolPool`，`tools/registry.py` 应拆成三个职责：

```python
def get_all_tools() -> list[MicroTool]:
    """返回所有已注册工具（不过滤）"""

def get_enabled_tools(config: ToolsConfig) -> list[MicroTool]:
    """按 config.yaml 的 tools: 开关过滤"""

def assemble_tool_pool(config: ToolsConfig) -> list[MicroTool]:
    """
    最终交给 Agent 的工具列表。
    注意：工具顺序应保持稳定（影响 LLM 的 prompt cache 命中率）。
    当前：按 name 字母序排列。
    """
```

### 1.3 强制权限执行链

参考 Claude Code `toolExecution.ts`，每次工具调用都应走固定执行链，而非各工具自行处理权限：

```
execute_tool(tool, args)
  ├─ 1. 参数类型校验（pydantic / 基础类型检查）
  ├─ 2. tool.validate_args(args)（工具自定义校验，可选）
  ├─ 3. run_pre_tool_hooks(tool, args)
  ├─ 4. permission_check(tool, args)
  │       ├─ autonomy=readonly  → 拒绝所有非只读工具
  │       ├─ is_destructive     → 检查 allowed_dirs，autonomy=supervised 时需用户确认
  │       └─ deny_rules 匹配   → 拒绝并记录
  ├─ 5. tool.forward(**args)（实际执行）
  ├─ 6. run_post_tool_hooks(tool, args, result)
  └─ 7. truncate_or_offload(result, tool.max_output_chars)
```

当前分散在各工具内部的权限检查（`allowed_dirs` 判断等）应统一收敛到步骤 4。

### 1.4 自主等级（Autonomy Levels）

参考 ZeroClaw 的三级模型，提供比 `allow_destructive: true/false` 更清晰的权限语义：

```yaml
agent:
  autonomy: supervised   # readonly | supervised | full
```

| 等级 | 说明 | 适用场景 |
|------|------|------|
| `readonly` | 只允许只读工具（`is_read_only=True`），拒绝一切写操作 | 演示、受限环境 |
| `supervised` | 写操作受 `allowed_dirs` 约束；`is_destructive` 操作需用户确认 | 默认值，日常使用 |
| `full` | 无限制，跳过用户确认（慎用） | 信任的自动化场景 |

Autonomy 等级是权限执行链第 4 步的前置判断，比逐工具配置更直观。

### 1.5 工具输出 Offload

超出 `max_output_chars` 的工具输出写入临时文件，只返回路径给 LLM：

```python
def truncate_or_offload(result: str, limit: int) -> str:
    """
    当前：超出 limit 时截断并附加 "[输出已截断，完整内容见: /tmp/...]"
    未来：可改为写入 memory/ 目录并在 Retrieval 层索引，
          使 LLM 在后续轮次可以按需检索完整内容。
    """
```

对 `file_manager`（读大文件）、`web_search`（长网页）尤为重要。

---

## 二、Hooks / 生命周期扩展

参考 Claude Code 的 30+ 生命周期 hook，为 MicroAgent 设计简化版：

### 2.1 核心 Hook 事件

```python
class HookEvent(Enum):
    SESSION_START    = "session_start"
    SESSION_END      = "session_end"
    PRE_TOOL_USE     = "pre_tool_use"
    POST_TOOL_USE    = "post_tool_use"
    PRE_COMPACT      = "pre_compact"
    POST_COMPACT     = "post_compact"
    # 未来可扩展：PERMISSION_DENIED, TURN_START, TURN_END 等
```

### 2.2 Hook 执行类型

参考 Claude Code 的四种类型，MicroAgent 先支持两种：

| 类型 | 说明 | 配置方式 |
|------|------|------|
| Python 函数 | 内部 hook，注册到 HookRegistry | 代码注册 |
| Shell 命令 | 外部 hook，执行子进程 | config.yaml `hooks:` 节 |

Shell hook 的退出码语义（借鉴 Claude Code）：
- `0`：成功，继续
- `2`：阻塞错误，将 stderr 内容报告给模型，影响模型下一步行为
- 其他非零：报告给用户，不影响模型

```yaml
# config.yaml 示例
hooks:
  post_tool_use:
    - command: "python scripts/log_tool_use.py"
  pre_compact:
    - command: "echo '开始压缩' >> session.log"
```

### 2.3 接口规划

```python
class HookRegistry:
    def register(self, event: HookEvent, fn: Callable) -> None: ...
    def run(self, event: HookEvent, **context) -> HookResult: ...

class HookResult:
    blocked: bool      # 是否阻塞后续执行
    message: str       # 报告给模型或用户的内容
```

---

## 三、斜杠命令 / Skill 系统

当前 `cli/app.py` 中斜杠命令是 hardcode 的 if-else 分支。参考 Claude Code 的 Skill 系统，应改为可注册、可扩展的结构。

### 3.1 命令注册

```python
@dataclass
class SlashCommand:
    name: str                        # "/compress" → name="compress"
    description: str
    aliases: list[str] = field(default_factory=list)
    context: str = "inline"          # "inline"（共享会话）或 "fork"（隔离执行）
    handler: Callable | None = None  # None 表示 LLM-driven（prompt 类型）
```

- **inline**：在当前会话上下文中执行，共享对话历史（适合 /compress, /memory）
- **fork**：在独立的模型调用中执行，不污染当前上下文（适合重型分析任务）

### 3.2 用户自定义 Skill（未来）

参考 Claude Code 的 `~/.claude/skills/` 目录，未来支持用户在 `skills/` 目录放置 Markdown 文件定义自定义命令：

```markdown
---
name: summarize
description: 总结当前对话的关键决策
context: inline
---

请总结我们这次对话中做出的所有技术决策，以 bullet point 格式输出。
```

---

## 四、Agent Loop 设计规范

（已在 memory-design.md 中记录不可变状态快照和显式 Terminal State，此处补充其他要点）

### 4.1 惰性导入（Lazy Import）

参考 Claude Code 对 OpenTelemetry（~400KB）和 gRPC（~700KB）的懒加载处理：重量级依赖不放在模块顶层 import，只在首次实际使用时导入。

对 MicroAgent 有意义的候选：
- `rank_bm25`：仅在 Retrieval 层首次查询时导入
- `web_search` 依赖（`duckduckgo_search` 等）：仅在工具调用时导入
- `nuitka` 相关：构建时依赖，运行时无需

```python
# 推荐：延迟导入
def query(self, text: str) -> list:
    from rank_bm25 import BM25Okapi  # 首次调用时才导入
    ...
```

### 4.2 Token Budget 跨轮追踪

除了压缩阈值检查外，应在整个 session 维度追踪 token 消耗，用于 `/memory` 命令展示和日志：

```python
@dataclass
class TokenBudget:
    context_window: int
    used_in_current_context: int    # 边界之后的 token 数
    total_consumed_session: int     # 本次 session 累计消耗（含已压缩部分）
    compact_count: int              # 本次 session 压缩次数
```

### 4.3 不可变状态快照

借鉴 Claude Code `query.ts` 的设计，Agent Loop 每次迭代开始时对状态做只读解构，迭代内不修改；只在迭代末尾整体替换推进。

```python
@dataclass
class AgentState:
    messages: list                        # 完整对话历史
    turn_count: int
    has_attempted_reactive_compact: bool
    terminal: "TerminalReason | None"     # None = 继续循环
```

好处：每次迭代状态是清晰快照，避免跨迭代意外修改，便于测试和调试。

### 4.4 显式终止状态

```python
class TerminalReason(Enum):
    NO_TOOL_USE      = "no_tool_use"       # 模型不再调用工具，正常结束
    MAX_TURNS        = "max_turns"         # 达到 max_turns 上限
    BUDGET_EXCEEDED  = "budget_exceeded"   # token 预算耗尽
    USER_INTERRUPT   = "user_interrupt"    # 用户 Ctrl+C
    CONTEXT_OVERFLOW = "context_overflow"  # 响应式压缩后仍溢出
```

终止原因由 Agent Loop 返回给 `cli/app.py`，用于展示提示或记录日志。当前 smolagents AgentRunner 以异常或布尔值隐式传递终止原因，应改为显式枚举。

---

## 五、运行时 Feature Flag

参考 Claude Code 的构建时 feature flag，MicroAgent 用更简单的运行时 flag（config.yaml 的 `features:` 节）：

```yaml
features:
  memory: true           # 记忆系统
  web_search: true       # 网页搜索工具
  file_manager: true     # 文件管理工具
  system_info: true      # 系统信息工具
  # 未来扩展：
  # multi_agent: false
  # voice_input: false
```

工具注册时根据 `features` 决定是否加载，做到**功能开关不需要改代码**。（当前 `ToolsConfig` 已经有这个结构，保持并规范化即可。）

---

## 六、多 Agent 基础设施（未来蓝图）

当前 MicroAgent 是单 Agent。参考 Claude Code 的 Task 系统，记录未来多 Agent 扩展的设计方向，以便当前代码保留扩展接口。

### 6.1 Task 存储设计

```python
@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str          # "pending" | "in_progress" | "completed"
    owner: str | None    # 持有该任务的 agent id
    blocks: list[str]    # 本任务完成后才能开始的任务 id
    blocked_by: list[str]
    metadata: dict
```

存储方式：SQLite `tasks` 表（与 episodic/semantic 同一个 DB 文件），复用 `SQLiteBackend`。

### 6.2 并发安全

多 Agent 同时读写时，SQLite WAL 模式原生支持并发读；写操作通过 SQLite 事务保证原子性，无需额外文件锁。

### 6.3 当前占位

即使现在不实现多 Agent，`MemoryManager` 的接口设计应避免假设"只有一个 Agent 写入"。SQLite 事务天然支持多 writer，无需改造存储层。

---

## 七、目录结构与配置查找

### 7.1 运行时目录布局

```
# 用户数据目录（主，跨 exe 版本持久）
~\.pheobe\MicroAgent\
├── config.yaml          # 主配置文件
├── models\              # GGUF 模型文件（路径相对于 config.yaml）
├── memory\              # 首次运行自动创建
│   └── microagent.db    # SQLite 记忆库
├── logs\                # 首次运行自动创建，按日期滚动
│   └── microagent-YYYY-MM-DD.log
└── skills\              # 用户自定义斜杠命令（预留）

# 发布包（exe 所在目录，仅含分发文件）
<任意目录>\
├── microagent-<variant>.exe
├── config.yaml          # fallback 模板 / 默认配置示例
└── README.txt
```

### 7.2 Config 查找顺序

启动时按优先级依次查找，找到第一个存在的 config.yaml 即停止：

1. `~\.pheobe\MicroAgent\config.yaml`（主用户目录）
2. `<exe所在目录>\config.yaml`（fallback，适合便携模式）
3. 都不存在 → 使用内置默认值，并提示用户自动创建主目录配置

```python
def find_config() -> Path:
    user_config = Path.home() / ".pheobe" / "MicroAgent" / "config.yaml"
    if user_config.exists():
        return user_config
    exe_config = Path(sys.executable).parent / "config.yaml"
    if exe_config.exists():
        return exe_config
    # 不存在则初始化用户目录
    return _bootstrap_user_dir()
```

### 7.3 首次运行初始化

检测到 `~\.pheobe\MicroAgent\` 不存在时，自动执行：

1. 创建完整目录树（`config/models/memory/logs/skills`）
2. 若 exe 同级存在 `config.yaml`，复制到用户目录作为初始配置
3. 否则写入内置默认配置模板，并打印提示

### 7.4 路径解析规则

config.yaml 中所有文件路径**相对于 config.yaml 自身所在目录**解析，与 config.yaml 实际位置无关。

```yaml
# config.yaml 位于 ~\.pheobe\MicroAgent\config.yaml
# 以下路径均相对于 ~\.pheobe\MicroAgent\
model:
  path: models\gemma-4-e2b-instruct.gguf   # → ~\.pheobe\MicroAgent\models\...
memory:
  db_path: memory\microagent.db             # → ~\.pheobe\MicroAgent\memory\...
```

这一规则已在 `core/config.py` 加载时实现（load time 解析，非 runtime）。

---

## 附：各设计点实现优先级

| 设计点 | 优先级 | 理由 |
|--------|--------|------|
| 目录结构与配置查找（§7） | 高 | 基础设施，影响所有路径相关逻辑 |
| 工具权限执行链（§1.3） | 高 | 安全基础，重构成本低 |
| 工具输出 Offload（§1.5） | 高 | 直接影响 context 消耗 |
| 自主等级（§1.4） | 高 | 比 allow_destructive 更清晰，改动小 |
| 斜杠命令注册化（§3.1） | 中 | 当前 hardcode 可用，但扩展困难 |
| Hooks 系统（§2） | 中 | 接口先定，实现可为空 stub |
| Token Budget 追踪（§4.2） | 中 | `/memory` 命令依赖此数据 |
| 惰性导入（§4.1） | 低 | 启动性能优化，非阻塞问题 |
| 用户自定义 Skill（§3.2） | 低 | 未来功能，接口预留即可 |
| 多 Agent Task 系统（§6） | 低 | 长期规划，当前不实现 |
