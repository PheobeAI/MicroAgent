我用Claude Code深度解读51万行Claude Code源码
2026 年 3 月 31 日，Anthropic 通过一次源码快照泄漏了 Claude Code 的完整代码。本文基于这份源码，从工程角度深入剖析这个 AI 编程助手的核心设计——它有多大、用了什么技术、以及最关键的"智能体循环"究竟是怎么运转的。
目录
项目概览
技术栈全景
目录结构详解
启动流程
核心：Agent Loop
工具调用系统
流式执行引擎
Thinking 推理模式
Task 系统
Compact 对话压缩
Skill 系统
Hooks 生命周期扩展
高级特性与 Feature Flag
关键文件速查表
总结：架构亮点与设计哲学
一、项目概览：规模、背景、定位
Claude Code 是 Anthropic 官方出品的 AI 编程 CLI 工具，支持终端、IDE（VS Code / JetBrains）、Web 多端运行。用户通过对话指令让 Claude 直接操作本地文件、执行命令、搜索代码、调用外部工具，完成编程任务。

代码规模


指标	数值
TypeScript/TSX 文件数	1,884 个
总行数	~512,685 行
源码目录大小	35 MB
主入口文件 src/main.tsx	786 KB / 4,683 行
超过 50 万行代码，这不是一个玩具项目——它是生产级工程的体量。

二、技术栈全景
核心技术选型


类别	技术	说明
运行时	Bun	替代 Node.js，启动更快，内置 bundler 和测试框架
语言	TypeScript（strict 模式）	全库严格类型，Zod 作为运行时 schema 校验
终端 UI	React + Ink	在终端中运行 React 组件树
CLI 解析	Commander.js	附带 extra-typings 的类型安全 CLI
Schema 校验	Zod v4	工具输入校验、配置校验
LLM 接入	@anthropic-ai/sdk	Anthropic 官方 SDK，支持流式输出
外部协议	MCP SDK + LSP	工具扩展协议 + 语言服务器协议
遥测	OpenTelemetry + gRPC	懒加载，不阻塞启动
Feature Flag	GrowthBook + bun:bundle	运行时灰度 + 构建时死代码消除
认证	OAuth 2.0 + JWT + macOS Keychain	多层安全存储
代码搜索	ripgrep	GrepTool 内部调用

显示详细信息
最有意思的技术决策：Bun 死代码消除
Claude Code 大量使用 Bun 的 bun:bundle 模块做构建时 feature flag 死代码消除。flag 在打包时就被判断并剔除，而不是运行时的 if/else 分支：

// src/tools.ts（节选）
import { feature } from 'bun:bundle'

const SleepTool = feature('PROACTIVE') || feature('KAIROS')
  ? require('./tools/SleepTool/SleepTool.js').SleepTool
  : null

const cronTools = feature('AGENT_TRIGGERS')
  ? [
      require('./tools/ScheduleCronTool/CronCreateTool.js').CronCreateTool,
      // ...
    ]
  : []
这意味着内部开发版和对外发布版是完全不同的二进制，对外版本里根本不含某些实验性功能的代码。

React + Ink：在终端里跑 React
Ink 把 React 的组件化思想搬进了终端。src/components/ 下有 140+ 个 React 组件：Spinner、Input、Prompt、Messages、Toolbars、Dialogs……

这让终端 UI 具备了现代 Web 应用的开发体验：状态管理、条件渲染、组件复用，全都是 React 的方式。

三、目录结构详解
src/
├── main.tsx                  # CLI 入口（4,683 行）
├── QueryEngine.ts            # LLM 会话引擎（1,295 行）
├── query.ts                  # Agent Loop（1,729 行）
├── Tool.ts                   # Tool 类型定义（792 行）
├── tools.ts                  # 工具注册与池化（390 行）
├── commands.ts               # 命令注册与分发（754 行）
│
├── tools/          (184 文件, 3.2MB)   # 40+ 工具实现
├── commands/       (189 文件, 3.3MB)   # 50+ 斜杠命令
├── components/     (389 文件, 11MB)    # React/Ink UI 组件
├── utils/          (564 文件, 7.8MB)   # 工具函数、配置、权限
├── services/       (130 文件, 2.2MB)   # MCP、LSP、OAuth、Compact
├── hooks/          (104 文件, 1.5MB)   # React hooks
├── bridge/                             # IDE 桥接层（VS Code/JetBrains）
├── screens/                            # 全屏 UI（REPL、Doctor、Resume）
├── skills/                             # Skill 系统
├── tasks/                              # Task 管理 UI 层
├── coordinator/                        # 多 Agent 协调（369 行）
├── ink/                                # Ink 渲染器封装
├── cli/                                # CLI 工具函数
├── keybindings/                        # 快捷键配置（含 Vim 模式）
└── ...
各目录职责一览：



目录	职责
tools/	每个子目录是一个独立工具（BashTool、FileReadTool 等），自包含
commands/	斜杠命令实现（/commit、/review、/doctor 等）
components/	所有终端 UI 组件，React + Ink 实现
utils/	认证、配置、权限规则、消息处理、环境检测等大量基础设施
services/	与外部系统交互：Anthropic API、MCP 服务器、LSP、OAuth、Compact
bridge/	IDE 插件桥接，JWT 认证双向消息协议
coordinator/	多 Agent 协调器（实验性，feature-gated）
四、启动流程：main.tsx 的性能优化
文件：src/main.tsx（4,683 行）

Claude Code 的启动流程经过细致的性能优化。一进入 main.tsx 就立即并行启动多个预取任务，不等 CLI 参数解析完成：

// 并行预取（~40ms vs 串行 135ms+）
const mdmPrefetch    = startMdmRawRead()          // MDM 企业策略
const keychainPrefetch = startKeychainPrefetch()  // OAuth / API Key
// GrowthBook feature flags 也在此时异步拉取
整个启动链路：

main.tsx 入口
  ├─ profileCheckpoint('main_tsx_entry')   ← 启动计时打点
  ├─ 并行预取（MDM、Keychain、GrowthBook）
  ├─ Commander.js 解析 CLI 参数
  ├─ 按命令类型分发：
  │   ├─ 普通交互：React/Ink REPL 渲染
  │   ├─ --resume：恢复上次会话
  │   ├─ --bridge：IDE 桥接模式
  │   └─ 子命令：/mcp、/config、/doctor 等
  └─ Bootstrap：加载 MCP 配置、权限规则、OAuth 状态
懒加载：OpenTelemetry（~400KB）和 gRPC（~700KB）均采用懒加载，不出现在冷启动路径上。项目内置 startupProfiler，通过 checkpoint 记录每个启动阶段耗时，持续追踪性能回归。

五、核心：Agent Loop（智能体循环）
这是整个系统最核心的部分——理解了 Agent Loop，就理解了 Claude Code 的运作本质。

5.1 整体思路：ReAct 循环
Claude Code 的 Agent Loop 实现了经典的 ReAct 模式（Reasoning + Acting）：

用户输入
   ↓
[调用 LLM，流式获取响应]
   ↓
响应中有 tool_use？
   ├─ 是 → 执行工具 → 将结果追加到对话 → 回到"调用 LLM"
   └─ 否 → 结束，将最终文本响应展示给用户
每次"调用 LLM → 执行工具 → 返回结果"是一个 turn，Agent Loop 就是把多个 turn 串联起来的无限循环。

5.2 入口：QueryEngine.submitMessage()
文件：src/QueryEngine.ts:209

QueryEngine 是对话会话的容器，持有消息历史、工具列表、权限控制器等状态。每次用户输入都通过 submitMessage() 进入：

// QueryEngine.ts:209
async *submitMessage(
  prompt: string | ContentBlockParam[],
  options?: { uuid?: string; isMeta?: boolean },
): AsyncGenerator<SDKMessage, void, unknown> {
  // 包装 canUseTool，追踪权限拒绝记录
  const wrappedCanUseTool: CanUseToolFn = async (...) => {
    const result = await canUseTool(...)
    if (result.behavior === 'deny') {
      this.permissionDenials.push(...)  // 记录拒绝历史
    }
    return result
  }
  // 进入 query() → queryLoop()
  yield* query({ messages, tools, canUseTool: wrappedCanUseTool, ... })
}
5.3 核心循环：queryLoop()
文件：src/query.ts:241

queryLoop 是一个 async generator 函数，yield 出流式事件供 UI 层消费，return 一个 Terminal（终止原因）：

// query.ts:241
async function* queryLoop(
  params: QueryParams,
  consumedCommandUuids: string[],
): AsyncGenerator<StreamEvent | Message | ..., Terminal>
循环状态机初始化（query.ts:268）：

let state: State = {
  messages,                     // 完整对话历史
  toolUseContext,               // 工具上下文（工具列表、权限回调、agent ID 等）
  maxOutputTokensOverride,      // 恢复场景的 token 覆盖值
  autoCompactTracking,          // 自动压缩跟踪
  stopHookActive,               // stop hook 激活状态
  maxOutputTokensRecoveryCount, // 恢复重试计数
  hasAttemptedReactiveCompact,  // 是否已尝试响应式压缩
  turnCount,                    // 当前第几轮（从 1 开始）
  transition,                   // 本次迭代的来源描述
}
状态的关键设计：每次迭代开始时解构 state 拿到只读引用，迭代内不修改 state；只在"continue sites"（循环末尾）通过 state = { ...newState } 整体替换。这保证了每次迭代的状态是清晰快照，避免了跨迭代的意外修改。

主循环骨架（query.ts:307）：

while (true) {
  // 1. 解构当前状态（只读）
  const { messages, toolUseContext, turnCount, ... } = state

  // 2. 预取：skill discovery（后台并发，不阻塞）
  const pendingSkillPrefetch = skillPrefetch?.startSkillDiscoveryPrefetch(...)

  yield { type: 'stream_request_start' }

  // 3. 只取 compact 边界之后的消息（节省 token）
  let messagesForQuery = [...getMessagesAfterCompactBoundary(messages)]

  // 4. 调用 LLM API（流式）
  const streamingToolExecutor = new StreamingToolExecutor(tools, canUseTool, toolUseContext)
  for await (const event of deps.callModel({ model, systemPrompt, messages: messagesForQuery, tools, ... })) {
    yield event  // 流式输出给 UI
    if (event.type === 'content_block_start' && event.content_block.type === 'tool_use') {
      streamingToolExecutor.addTool(event.content_block, assistantMessage)
    }
  }

  // 5. 等待所有工具执行完成，收集结果
  for await (const update of streamingToolExecutor.getRemainingResults()) {
    yield update.message
    toolUseContext = update.newContext
  }

  // 6. 判断退出 or 继续
  if (toolUseBlocks.length === 0) {
    return { type: 'no_tool_use' }  // 模型不再调用工具，结束
  }
  if (turnCount >= maxTurns) {
    return { type: 'max_turns' }    // 达到轮次上限，结束
  }

  // 7. 将工具结果追加到消息，进入下一轮
  state = { ...state, messages: [...messages, ...toolResultMessages], turnCount: turnCount + 1 }
}
5.4 Token Budget 跟踪
循环内还有一个贯穿全程的 budgetTracker（src/utils/tokenBudget.ts），用于追踪每轮消耗的 token 数，配合 taskBudgetRemaining 在跨 compact 边界后也能准确统计总消耗。当预算耗尽时，循环以 { type: 'budget_exceeded' } 终止。

六、工具调用系统：Tool Interface & Permission Model
6.1 Tool 接口定义
文件：src/Tool.ts:362

每个 tool 是一个实现了特定接口的对象：

type Tool<Input, Output, P> = {
  name: string
  aliases?: string[]               // 向后兼容别名

  // 核心执行函数
  call(
    args: Input,
    context: ToolUseContext,
    canUseTool: CanUseToolFn,
    parentMessage: AssistantMessage,
    onProgress: ProgressCallback,
  ): Promise<ToolResult<Output>>

  description(input: Input, options: DescriptionOptions): string
  inputSchema: ZodType<Input>      // 输入校验 schema

  isConcurrencySafe(input: Input): boolean  // 是否可与其他工具并发
  isReadOnly(input: Input): boolean          // 是否只读操作
  isDestructive?(input: Input): boolean      // 是否不可逆
  interruptBehavior?(): 'cancel' | 'block'   // 用户中断时的行为
  maxResultSizeChars: number                 // 结果大小上限
}
工具结果类型：

type ToolResult<T> = {
  data: T
  newMessages?: Message[]                             // 可附加额外消息
  contextModifier?: (ctx: ToolUseContext) => ToolUseContext  // 可修改上下文
}
6.2 工具注册：tools.ts
文件：src/tools.ts（390 行）

所有工具通过三个函数组装成"工具池"：

**getAllBaseTools()**：返回所有内置工具实例（40+）
**getTools(context)**：按权限规则、feature flags、运行模式过滤
**assembleToolPool(context, mcpTools)**：合并内置工具 + MCP 外部工具，去重排序（排序保证 prompt cache 命中率稳定）
内置工具分类（40+ 个）：



类别	工具
文件操作	FileReadTool、FileEditTool、FileWriteTool、NotebookEditTool
Shell 执行	BashTool、PowerShellTool
搜索	GlobTool、GrepTool、WebFetchTool、WebSearchTool、ToolSearchTool
Agent 协作	AgentTool、SendMessageTool、AskUserQuestionTool
计划模式	EnterPlanModeTool、ExitPlanModeTool、TodoWriteTool
Git 工作区	EnterWorktreeTool、ExitWorktreeTool
任务管理	TaskCreateTool、TaskUpdateTool、TaskGetTool、TaskListTool、TaskStopTool、TaskOutputTool
定时调度	CronCreateTool、CronDeleteTool、CronListTool、RemoteTriggerTool
MCP 集成	MCPTool、ListMcpResourcesTool、ReadMcpResourceTool、McpAuthTool
IDE / LSP	LSPTool
其他	BriefTool、ConfigTool、SkillTool

显示详细信息
6.3 权限执行链
每次工具调用都经过以下完整权限检查链（src/services/tools/toolExecution.ts）：

runToolUse(block)
  ├─ 1. Zod schema 校验输入参数
  ├─ 2. tool.validateInput()（工具自定义校验，可选）
  ├─ 3. runPreToolUseHooks()     ← 前置 hooks
  ├─ 4. canUseTool() 权限决策
  │       ├─ deny 规则匹配 → 拒绝（记入 permissionDenials）
  │       ├─ ask 规则匹配  → 弹出用户确认对话框（阻塞）
  │       └─ allow         → 通过
  ├─ 5. tool.call(input, context, ...)  ← 实际执行
  ├─ 6. runPostToolUseHooks()    ← 后置 hooks
  └─ 7. 格式化为 tool_result 消息块，返回给 LLM
权限规则的细粒度令人印象深刻。用户可以配置针对特定工具、特定参数模式的规则，例如：

"Bash(git *)" — 自动允许所有 git 命令
"Bash(rm *)" — 所有删除命令必须询问
"Read" — 所有文件读取自动允许
6.4 大结果处理
每个工具有 maxResultSizeChars 上限。超出时（如读取超大文件），结果内容写入磁盘临时文件，API 只收到包含文件路径的摘要（src/utils/toolResultStorage.ts），避免单个工具结果撑爆 context window。

七、流式执行引擎：StreamingToolExecutor
文件：src/services/tools/StreamingToolExecutor.ts

这是工具调用系统中最精妙的部分：在 LLM 流式输出的同时，就开始并发执行工具，不等全部 tool_use block 到齐。

7.1 核心设计
export class StreamingToolExecutor {
  private tools: TrackedTool[] = []   // 工具执行队列
  private toolUseContext: ToolUseContext
  private hasErrored = false
  private siblingAbortController: AbortController  // 兄弟工具出错时中止其他工具

  // 每个被追踪的工具状态
  // 'queued' → 'executing' → 'completed' → 'yielded'
}

type TrackedTool = {
  id: string
  block: ToolUseBlock
  status: ToolStatus
  isConcurrencySafe: boolean
  promise?: Promise<void>           // 执行 Promise
  results?: Message[]               // 执行结果（缓存）
  pendingProgress: Message[]        // 进度消息（立即推送）
  contextModifiers?: Array<(ctx: ToolUseContext) => ToolUseContext>
}
7.2 并发控制逻辑
// StreamingToolExecutor.ts:76
addTool(block: ToolUseBlock, assistantMessage: AssistantMessage): void {
  const isConcurrencySafe = toolDefinition.isConcurrencySafe(parsedInput)
  this.tools.push({ id, block, status: 'queued', isConcurrencySafe, ... })
  void this.processQueue()  // 立即尝试调度
}

// 并发条件判断（:129）
private canExecuteTool(isConcurrencySafe: boolean): boolean {
  const executingTools = this.tools.filter(t => t.status === 'executing')
  return (
    executingTools.length === 0 ||
    (isConcurrencySafe && executingTools.every(t => t.isConcurrencySafe))
  )
}
核心规则：

只读（并发安全）工具：只要当前正在执行的全是只读工具，就可以立即加入并发执行
写入（非并发安全）工具：必须等所有在执行的工具完成，才能独占执行
非并发工具后面的所有工具：必须串行等待（维护顺序）
7.3 错误传播：兄弟工具联动取消
StreamingToolExecutor 持有一个 siblingAbortController——当一个 BashTool 执行出错时，会通过这个 controller 立即取消所有正在并发执行的兄弟工具进程，避免无效工作继续消耗资源。

这个 controller 是父级 toolUseContext.abortController 的子级：兄弟取消不会影响整个 query 的生命周期，只是当前批次的工具被取消。

7.4 结果顺序保证
getRemainingResults() 按工具接收顺序（非完成顺序）yield 结果。即使并发执行，结果的顺序始终与 LLM 发出 tool_use 的顺序一致，保证了 LLM 下一轮收到的 tool_result 对应关系是确定的。

八、Thinking 推理模式
文件：src/utils/thinking.ts

Claude Code 支持 Claude 的 Extended Thinking 功能——让模型在给出最终回答之前进行"内部推理"，用于处理复杂问题。

8.1 ThinkingConfig 类型
type ThinkingConfig =
  | { type: 'adaptive' }                      // 自适应（模型自行决定是否思考）
  | { type: 'enabled'; budgetTokens: number } // 显式启用，指定思考 token 上限
  | { type: 'disabled' }                      // 关闭
8.2 ultrathink 关键字触发
src/utils/thinking.ts 还实现了一个彩蛋功能：用户在消息中输入 ultrathink 关键字，会触发最大 budget 的 thinking 模式：

// thinking.ts:29
export function hasUltrathinkKeyword(text: string): boolean {
  return /\bultrathink\b/i.test(text)
}
这个功能通过双重门控：构建时 feature('ULTRATHINK') 检查 + 运行时 GrowthBook 实验 tengu_turtle_carbon 检查，只对特定用户开放。

8.3 Thinking Blocks 的跨轮次保留
Thinking blocks（模型内部推理内容）在单次助手响应轨迹内跨 tool_use 轮次保留，确保模型在多轮工具调用后仍能"记住"自己之前的推理过程，不会在中间某轮 tool 执行后"失忆"。

九、Task 系统：多 Agent 协作基础设施
核心文件：src/utils/tasks.ts（862 行）

Task 是多 Agent 协作场景下的"工作单元"。当一个 orchestrator agent 把大任务拆分给多个 worker agent 时，通过 Task 系统追踪每个子任务的状态。

9.1 存储设计
Task 以 JSON 文件形式存储于 ~/.claude/config/tasks/{taskListId}/ 目录：

type Task = {
  id: string
  subject: string                           // 简短标题
  description: string                       // 详细描述
  activeForm?: string                       // 当前进行中的操作，如 "Running tests"
  owner?: string                            // 持有该任务的 agent ID
  status: 'pending' | 'in_progress' | 'completed'
  blocks: string[]                          // 本任务完成后才能开始的任务
  blockedBy: string[]                       // 必须先完成才能开始本任务的任务
  metadata?: Record<string, unknown>
}
9.2 并发安全：文件锁
多个 agent 可能同时读写 task，所有修改操作都在 proper-lockfile 的文件锁保护下执行：

最多重试 30 次
重试间隔指数退避
create / update / delete 全部原子完成
9.3 原子 Claim
claimTask() 实现了原子性的任务认领——多个 agent 竞争同一 task 时，只有一个能成功：

// tasks.ts:541
async function claimTask(taskId, agentId, taskListId) {
  await lock(taskFilePath)
  try {
    const task = await readTask(taskId)
    if (task.owner && task.owner !== agentId) {
      return { success: false, reason: 'already_claimed' }
    }
    await writeTask({ ...task, owner: agentId, status: 'in_progress' })
    return { success: true }
  } finally {
    await unlock(taskFilePath)
  }
}
9.4 级联清理与通知
删除 task 时自动清理所有其他任务中对该 task 的 blocks/blockedBy 引用
onTasksUpdated 信号：同进程内的订阅者（如 UI 层）立即感知任务变更
Hook 集成：TaskCreatedHook、TaskCompletedHook 在任务创建/完成时触发
十、Compact：对话压缩的四种策略
核心文件：src/services/compact/compact.ts、src/commands/compact/compact.ts（288 行）

当 context window 接近上限时，Compact 用 LLM 对历史对话做摘要，把长历史压缩为简洁总结后继续工作。

四种压缩策略


策略	触发场景	特点
Session Memory Compaction	首选	不调用 LLM，直接存入 session memory 文件，最快
Microcompaction	含大量图片/文档时	先剥离图片（替换为 [image]），再做轻量压缩
Traditional Compaction	需高质量摘要	fork 独立子 agent 做全量摘要，支持自定义指令
Reactive Compaction	收到 prompt_too_long 错误	响应式触发，自动压缩后重试
关键常量与 Hooks 集成
const COMPACT_MAX_OUTPUT_TOKENS = 20_000    // 摘要最大输出 token
const POST_COMPACT_TOKEN_BUDGET = 50_000    // 压缩后可用 token 预算
**executePreCompactHooks()**：压缩前触发，可注入自定义摘要指令（如"重点保留测试相关上下文"）
**executePostCompactHooks()**：压缩后触发，通知下游系统
压缩前会自动将 user 消息中的图片替换为占位符，避免摘要本身又触发 prompt-too-long。

十一、Skill 系统：斜杠命令与可复用工作流
关键文件：

src/skills/bundledSkills.ts — 内置技能注册
src/skills/loadSkillsDir.ts — 从磁盘加载用户自定义 skill
src/utils/slashCommandParsing.ts — 解析 /command args 语法
src/utils/processUserInput/processSlashCommand.tsx — 执行入口
Skill 数据结构
type Command = {
  type: 'prompt' | 'local'       // prompt = LLM 驱动；local = 本地函数
  name: string
  description: string
  whenToUse: string
  source: 'bundled' | 'skills' | 'commands' | 'plugin' | 'managed' | 'mcp'
  context: 'inline' | 'fork'    // 执行模式
  allowedTools: string[]         // 可用工具白名单
  model?: string                 // 可指定模型覆盖
  agent?: string                 // 可指定 agent 类型
}
两种执行模式
context: 'inline'（默认）：在当前会话上下文中直接执行，共享对话历史
**context: 'fork'**：在独立子 agent 中运行，完全隔离，适合耗时后台任务
Skill 来源


来源	说明
bundled	内置技能：/commit、/review、/doctor、/compact 等
skills	用户在 ~/.claude/skills/ 目录下的自定义 Markdown 文件
plugin	插件提供的技能
managed	平台管理员配置的技能
mcp	MCP Server 工具自动生成的 skill
MCP Skills 最有意思：配置了 MCP Server 后，其所有工具自动注册为可调用的 skill，通过 /toolname (MCP) 语法触发——零配置扩展。

十二、Hooks：生命周期扩展点
文件：src/utils/hooks/（多文件，含 hookEvents.ts、hooksConfigManager.ts 等）

Hooks 是整个系统的扩展机制，覆盖 30+ 生命周期事件：

PreToolUse / PostToolUse / PostToolUseFailure
SessionStart / SessionEnd / Setup / Stop / StopFailure
SubagentStart / SubagentStop
TaskCreated / TaskCompleted
PreCompact / PostCompact
UserPromptSubmit
PermissionDenied / PermissionRequest
InstructionsLoaded / CwdChanged / FileChanged
TeammateIdle
Hook 配置（在 .claude/config.yaml 的 hooks 节）支持四种执行类型：

类型	说明
Shell 命令	直接执行子进程，输入通过 stdin 传入
HTTP 请求	POST 到指定 endpoint
Agent 委托	把事件交给另一个子 agent 处理
Prompt Hook	标准 JSON 协议与 LLM 交互
Exit code 语义：

0：成功
2：阻塞错误，报告给模型，影响模型下一步行为
其他非零：报告给用户，不影响模型
这种设计使 CI 系统、安全扫描工具、代码审查工具等可以无缝接入 Claude Code 工作流，只需实现一个 Shell 脚本即可。

十三、高级特性与 Feature Flag
这些功能通过 bun:bundle feature flag 门控，仅在特定构建中存在。



Feature Flag	功能描述
KAIROS	完整的语音/助手模式，包含主动推送通知能力
BRIDGE_MODE	VS Code / JetBrains IDE 桥接层
COORDINATOR_MODE	多 Agent 编排协调器
PROACTIVE	主动型 Agent 模式（无需用户发起）
VOICE_MODE	语音输入支持
ULTRATHINK	最大 budget 的 Extended Thinking
ULTRAPLAN	高级规划模式
AGENT_TRIGGERS	定时调度 Agent（Cron 触发）
AGENT_TRIGGERS_REMOTE	远程事件触发 Agent
MONITOR_TOOL	监控工具
KAIROS_GITHUB_WEBHOOKS	GitHub Webhook 集成
BUDDY	终端伴侣精灵（彩蛋）

显示详细信息
IDE 桥接层（BRIDGE_MODE）
文件：src/bridge/（12,613 行）

VS Code / JetBrains 插件通过 JWT 认证的双向消息协议与 CLI 通信：

权限确认对话框在 IDE 侧弹出，而不是终端
sessionRunner.ts 管理完整的会话生命周期
核心 Agent Loop 只有一份（在 CLI 中），IDE 插件是薄前端层
多 Agent 协调（COORDINATOR_MODE）
文件：src/coordinator/（369 行）

通过 AgentTool 派生子 agent，子 agent 有独立 context window，通过 Task 系统和共享文件系统与父 agent 通信。实验性的 TeamCreateTool 支持创建一组 agent 并行协作，类似软件开发团队。

MCP 集成
文件：src/services/mcp/

支持四种传输方式：StdioClientTransport（最常用）、SSEClientTransport、StreamableHTTPClientTransport、WebSocketTransport。连接的 MCP 工具被动态转换为原生 Tool 定义，与内置工具无缝混用。

十四、关键文件速查表
文件	行数	职责
src/main.tsx	4,683	CLI 入口、React/Ink 渲染、并行预取
src/QueryEngine.ts	1,295	LLM 会话引擎，持有消息历史和权限记录
src/query.ts	1,729	Agent Loop 核心（queryLoop）
src/Tool.ts	792	Tool 类型定义与工具查找
src/tools.ts	390	工具注册、池化、feature gate
src/commands.ts	754	斜杠命令注册与分发
src/services/tools/toolExecution.ts	1,745	工具权限检查、hooks、实际执行
src/services/tools/toolOrchestration.ts	189	工具并发/串行分批调度
src/services/tools/StreamingToolExecutor.ts	~300	流式并发工具执行引擎
src/utils/tasks.ts	862	Task 系统（文件锁 + 原子 claim）
src/services/compact/compact.ts	200+	对话压缩服务（四种策略）
src/utils/thinking.ts	~200	Thinking 模式配置与 ultrathink 触发
src/utils/hooks.ts	200+	Hooks 系统主入口
src/screens/REPL/REPL.tsx	5,005	交互式 REPL 界面（调用 query()）

显示详细信息
十五、总结：架构亮点与设计哲学
读完 Claude Code 的源码，能感受到几个贯穿全局的设计哲学：

1. Async Generator 驱动整个架构
Agent Loop、工具执行、流式输出，全部通过 async function* 串联。yield 事件给 UI 层，return 终止状态给调用方，既保持代码的线性可读性，又实现了真正的流式处理。这是 TypeScript 中处理"持续产生数据的长流程"的最优解。

2. 流式工具执行：边收 LLM 输出边执行工具
StreamingToolExecutor 的设计极具工程价值——LLM 还在流式输出 token 时，已经开始并发执行已知的工具了。这大幅降低了感知延迟，尤其在 LLM 同时调用多个只读工具时效果显著。

3. 权限模型是硬编码的必经路径
权限检查不是可选的附加层，而是工具调用路径上不可绕过的节点。每个工具调用都必须经过：Zod 校验 → tool 自检 → pre-hooks → canUseTool → 执行 → post-hooks。安全是设计的出发点，而不是事后的补丁。

4. 构建时特性隔离
通过 Bun 的 bun:bundle feature flag，实验性功能在构建时就被消除，对外版本的二进制里根本不含相关代码。这不仅减少了包体积，也防止了通过逆向工程探测未发布功能。

5. 多 Agent 是一等公民
Task 系统的文件锁、原子 claim、blocking 依赖关系；StreamingToolExecutor 的兄弟 abort 机制；coordinator 的团队协作模型……这些都是为多 Agent 场景专门设计的基础设施，而不是单 Agent 的事后扩展。

6. 扩展性贯穿始终
MCP 接入任意外部工具，Hooks 覆盖所有生命周期，Skill 允许用户自定义工作流，Plugin 系统支持三方扩展。Claude Code 构建了一个开放的平台，而不是一个封闭的工具。

代码索引提示：本文所有引用均附有源码路径和行号（如 src/query.ts:241），可直接在项目中定位验证。
