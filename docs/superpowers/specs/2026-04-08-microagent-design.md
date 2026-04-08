# MicroAgent 设计文档

**日期：** 2026-04-08
**状态：** 已确认

---

## 1. 项目目标

构建一个极致轻量的本地 AI Agent，可在 AMD R7 8845H（16GB RAM）轻薄本上流畅运行，打包为独立 `.exe` 文件，面向两类用户：

- **个人效率工具**：开发者自用，处理文件、查资料、系统监控等日常任务
- **分发给他人**：打包后分享给非技术用户，要求开箱即用

---

## 2. 技术栈

| 组件 | 选型 |
|---|---|
| Agent 框架 | smolagents（ToolCallingAgent 模式） |
| 推理后端 | llama-cpp-python（GGUF 格式，Vulkan 后端） |
| 首选模型 | Gemma-4-E2B-Instruct（或同级别 2B 移动端优化模型） |
| 硬件加速 | Vulkan（AMD Radeon 780M iGPU） |
| CLI 渲染 | rich |
| 系统信息 | psutil |
| 配置校验 | pydantic |
| 打包工具 | Nuitka |

**Agent 模式选择：** 使用 `ToolCallingAgent`（LLM 输出结构化 JSON 工具调用），而非 `CodeAgent`。原因：2B 小模型生成 JSON 比生成可执行 Python 代码更可靠，结果更可预测，打包链路更简单。配置项预留 `mode: code` 供未来升级。

---

## 3. 整体架构

```
MicroAgent/
├── core/
│   ├── agent.py        # AgentRunner 抽象 + ToolCallingAgent 实现
│   ├── model.py        # ModelBackend 抽象 + LlamaCpp 实现
│   └── config.py       # 配置加载与 pydantic 校验
├── tools/
│   ├── base.py         # MicroTool 基类（继承 smolagents.Tool）
│   ├── web_search.py   # DuckDuckGo（默认）+ Tavily（有 Key 时自动切换）
│   ├── file_manager.py # 文件系统工具集
│   └── system_info.py  # CPU / 内存 / 电池状态
├── cli/
│   └── app.py          # CLI 交互主循环
├── config.yaml         # 用户配置文件
└── main.py             # 入口：加载配置 → 组装 Agent → 启动 CLI
```

### 扩展点

| 升级场景 | 做法 |
|---|---|
| 切换到 CodeAgent | 修改 `config.yaml` 的 `agent.mode: code`，`AgentRunner` 内部切换实现 |
| 换用 Ollama / OpenAI API | 实现新的 `ModelBackend` 子类，接口不变 |
| 新增工具 | 继承 `MicroTool`，在 `config.yaml` 的 `tools:` 下启用 |
| 后续加 Web UI | CLI 是 `AgentRunner` 的一个消费者，Web UI 可平行接入同一接口 |

---

## 4. 配置系统

配置文件为 `config.yaml`，放置在 exe 同级目录。启动时自动查找：找到则加载并与默认值合并；找不到则使用全部默认值，首次运行时提示用户可创建配置文件。用 pydantic 做 schema 校验，配置错误时输出明确提示。

```yaml
model:
  path: ./models/gemma-4-e2b-instruct.gguf
  n_gpu_layers: -1      # -1 = 全部卸载到 GPU
  n_threads: 6
  n_ctx: 4096
  max_tokens: 512

agent:
  mode: tool_calling    # 可改为 "code" 升级到 CodeAgent
  verbose: true

tools:
  web_search:
    enabled: true
    tavily_api_key: ""  # 留空则自动使用 DuckDuckGo
  file_manager:
    enabled: true
    allow_destructive: false   # 开启后才能使用写入/删除/移动操作
    allowed_dirs: []           # 破坏性操作的目录白名单，空 = 不限制
  system_info:
    enabled: true

runtime:
  language: zh
  log_level: info
```

---

## 5. 工具系统

### 5.1 工具基类

```python
# tools/base.py
from smolagents import Tool

class MicroTool(Tool):
    """所有工具的基类，子类只需填 name/description/inputs/output_type 并实现 forward()"""
    pass
```

### 5.2 web_search

启动时检查 `tavily_api_key`，自动选择后端，两者对外接口完全相同：

- **有 Key** → TavilySearchResults（质量更好）
- **无 Key** → DuckDuckGoSearchRun（零配置）

### 5.3 file_manager

拆分为多个独立 Tool（smolagents 每个 Tool 只有一个 `forward()` 入口，拆开比合并更清晰）。

**权限矩阵：**

| 工具 | `allow_destructive: false` | `allow_destructive: true` |
|---|---|---|
| `list_directory(path)` | ✅ | ✅ |
| `read_file(path)` | ✅ | ✅ |
| `get_file_info(path)` | ✅ | ✅ |
| `find_files(directory, pattern)` | ✅ | ✅ |
| `write_file(path, content)` | ❌ | ✅（受 allowed_dirs 约束）|
| `append_file(path, content)` | ❌ | ✅（受 allowed_dirs 约束）|
| `create_directory(path)` | ❌ | ✅（受 allowed_dirs 约束）|
| `move_file(src, dst)` | ❌ | ✅（受 allowed_dirs 约束）|
| `delete_file(path)` | ❌ | ✅（受 allowed_dirs 约束）|

`delete_file` 只删文件，不递归删目录，防止误操作。破坏性工具在初始化时检查权限，未开启时抛出友好错误提示。

### 5.4 system_info

用 psutil 返回 CPU 使用率、内存占用、电池电量，格式化为自然语言字符串。

### 5.5 工具注册

```python
# main.py 组装阶段
tools = ToolRegistry(config).load()
# 根据 config.tools 中 enabled 字段自动实例化工具列表，传给 AgentRunner
```

---

## 6. CLI 交互界面

用 `rich` 实现彩色输出。

**启动输出：**
```
[MicroAgent] 正在加载模型: ./models/gemma-4-e2b-instruct.gguf ...
[MicroAgent] 模型加载完成 (2.3s) | 内存占用: 2.1GB | 工具: 12 个已启用
[MicroAgent] 输入 /help 查看命令，Ctrl+C 退出
────────────────────────────────────────
>
```

**内置命令：**

| 命令 | 功能 |
|---|---|
| `/help` | 显示可用命令和已加载工具列表 |
| `/tools` | 列出当前启用的工具及状态 |
| `/clear` | 清空对话历史 |
| `/config` | 显示当前配置摘要 |

**任务输出格式（`verbose: true`）：**
```
> 查一下当前目录有哪些 Python 文件

◆ 思考中...
  调用工具: find_files(".", "*.py")

◆ 结果:
  找到 3 个 Python 文件：main.py, core/agent.py, tools/web_search.py

────────────────────────────────────────
>
```

`verbose: false` 时只显示最终结果，适合非技术用户。

---

## 7. 打包策略

**工具：** Nuitka `--onefile` 模式，内置 Python 运行时。

**关键构建参数：**
```bash
python -m nuitka \
  --onefile \
  --include-data-files=config.yaml=config.yaml \
  --include-package=smolagents \
  --include-package=llama_cpp \
  --include-package=rich \
  --include-package=psutil \
  --enable-plugin=anti-bloat \
  --output-filename=microagent.exe \
  main.py
```

`llama_cpp` 依赖的 Vulkan `.dll` 通过 `--include-data-dir` 一并打包。开发环境使用专用 Vulkan wheel：
```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan
```

**分发结构：**
```
microagent-v1.0.zip
├── microagent.exe    # 约 80-150MB（含 Python 运行时）
├── config.yaml       # 用户配置文件（附注释说明）
├── models/           # 空目录，放置 GGUF 文件
└── README.txt        # 极简使用说明
```

模型文件不打包进 exe，用户将 `.gguf` 放入 `models/` 目录后即可运行。

---

## 8. 两步走路线图

**阶段一（当前设计范围）：** CLI MVP
- 本地模型加载（LlamaCpp + Vulkan）
- ToolCallingAgent + 工具系统
- 彩色 CLI 交互
- Nuitka 打包为独立 exe

**阶段二（未来）：** Web UI 或桌面 GUI
- 基于同一 `AgentRunner` 接口
- 考虑 FastAPI + 简单前端，或 Tkinter 原生窗口
