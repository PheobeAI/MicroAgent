# MicroAgent

> 把 AI Agent 的能力装进一个 .exe 文件，放在桌面上双击就能用。

在 AMD R7 8845H（或同级轻薄本）上本地运行 Gemma-4 等 GGUF 模型，支持工具调用、跨会话记忆，打包为无需安装的 Windows 可执行文件。

---

## 特性

- **零安装**：onefile exe，内置 Python 运行时，用户只需放好模型文件
- **本地推理**：llama-cpp-python + GGUF，支持 CUDA / Vulkan / CPU 三种加速后端
- **工具调用**：网页搜索、文件读写、系统信息，可扩展
- **跨会话记忆**：SQLite 持久化 episodes + facts，BM25 + 时间衰减混合检索
- **上下文压缩**：阈值自动触发 + `/compress` 手动压缩，支持 128K context 长对话
- **三种分发变体**：cuda（NVIDIA）、vulkan（AMD / iGPU）、cpu（无 GPU）

---

## 系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11 x64 |
| 内存 | 推荐 16GB（模型占用 ≤ 4GB） |
| GPU | 可选；NVIDIA 用 cuda 变体，AMD / Intel iGPU 用 vulkan 变体 |
| 模型文件 | `.gguf` 格式，推荐 Gemma-4 E2B Instruct |

---

## 快速开始（直接使用）

1. 从 [Releases](../../releases) 下载对应 GPU 变体的 exe
2. 双击运行，程序自动在 `~\.pheobe\MicroAgent\` 创建配置目录
3. 将 `.gguf` 模型文件放入 `~\.pheobe\MicroAgent\models\`
4. 编辑 `~\.pheobe\MicroAgent\config.yaml` 填写模型路径（已有示例注释）
5. 再次运行即可使用

> **便携模式**：将 `config.yaml` 放在 exe 同级目录，程序优先读取用户目录配置，fallback 到 exe 同级。

```
> 帮我查一下今天的天气
◆ 思考中...
  调用工具: web_search("今天天气")
◆ 结果: ...
```

---

## 快速开始（开发）

```bash
git clone <repo-url>
cd MicroAgent

# 自动检测 GPU，创建 .venv，安装依赖
setup.bat

# 放置模型文件
copy path\to\your-model.gguf models\

# 激活 venv 并运行
.venv\Scripts\activate.bat
python main.py
```

指定变体（跳过自动检测）：

```bash
setup.bat cuda     # NVIDIA GPU
setup.bat vulkan   # AMD / iGPU
setup.bat cpu      # 无 GPU
```

运行测试：

```bash
pytest tests/ -v
```

---

## 构建

```bash
# 开发构建（目录模式，快速启动）
build.bat cuda | vulkan | cpu

# 发布构建（onefile，可分发）
build.bat cuda release
build.bat all release   # 三种变体顺序构建
```

产物：`dist\<variant>\microagent-<variant>.exe`

推送 `v*` tag 自动触发 GitHub Actions 并行构建三个变体并发布 Release：

```bash
git tag v0.x.y
git push origin v0.x.y
```

---

## 架构概览

```
用户输入（CLI）
    ↓
main.py → AgentRunner → LlamaCppBackend（Gemma-4）
                ↓               ↓
           Tool 调用        MemoryManager
           (web/file/sys)   ├── ContextManager（session 压缩）
                            └── MemoryStore（SQLite 持久化）
```

| 模块 | 职责 |
|---|---|
| `core/model.py` | llama-cpp-python 封装，解析 Gemma 工具调用格式 |
| `core/agent.py` | `AgentRunner` 抽象 + `ToolCallingAgentRunner` 实现 |
| `core/config.py` | pydantic 配置模型，路径相对 config.yaml 解析 |
| `tools/` | 各工具继承 `MicroTool`，注册到 `tools/registry.py` |
| `cli/app.py` | Rich 交互主循环，斜杠命令处理 |
| `memory/` | 记忆与上下文管理（设计中） |

新增工具：继承 `MicroTool` → 实现 `forward()` → 注册到 `registry.py` → 在 `config.yaml` 添加开关。

---

## 文档

| 文档 | 说明 |
|---|---|
| [docs/vision.md](docs/vision.md) | 项目定位、设计原则、技术选型理由 |
| [docs/memory-design.md](docs/memory-design.md) | 记忆与上下文系统设计 |
| [docs/engineering-design.md](docs/engineering-design.md) | 工程设计规范（工具系统、Hooks、Agent Loop 等） |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发环境搭建、构建、CUDA 注意事项 |

---

## CUDA 构建说明

llama-cpp-python 的 Windows CUDA 预编译 wheel 最高只到 v0.3.4，不支持 Gemma-4 架构，因此 CUDA 变体从源码编译。

**本地构建需要：** CUDA Toolkit 12.x + VS 2022 Build Tools（含 C++ 工作负载）+ CMake 3.20+

`install-deps.bat cuda` 会自动处理其余步骤（包括按需安装 Ninja）。

**CI 说明：** GitHub Actions 使用 `Jimver/cuda-toolkit` + `method: 'local'`，避免 Windows Server 2025 上网络安装器组件包名不可靠的问题（会导致退出码 `0xE0E00019`）。
