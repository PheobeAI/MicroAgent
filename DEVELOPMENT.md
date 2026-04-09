# MicroAgent 开发文档

## 前提条件（一次性安装）

| 工具 | 最低版本 | 用途 |
|---|---|---|
| Python | 3.10+ | 运行时与构建 |
| Git | 任意 | 版本控制 |
| VS 2022 Build Tools | 17.x（含 C++ 工作负载） | Vulkan 变体编译 llama-cpp-python |
| CMake | 3.20+ | Vulkan 变体构建系统 |
| winget | 内置于 Windows 11 | 自动安装 Vulkan SDK |

下载链接：
- VS 2022 Build Tools：https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
- CMake：https://cmake.org/download/（勾选 "Add CMake to system PATH"）

> **注：** CUDA 变体无需安装 CUDA Toolkit——使用官方预编译 wheel，任何 Windows 机器均可安装。

---

## 快速开始

```cmd
git clone <repo-url>
cd MicroAgent

:: 自动检测 GPU，创建 .venv，安装依赖
setup.bat

:: 放置模型文件（.gguf 格式）
copy path\to\your-model.gguf models\

:: 激活 venv 并运行
.venv\Scripts\activate.bat
python main.py
```

指定 GPU 变体（跳过自动检测）：

```cmd
setup.bat cuda      :: NVIDIA GPU（4070 TS、4080 等）
setup.bat vulkan    :: AMD Radeon（含 iGPU 780M 等）
setup.bat cpu       :: 无 GPU
```

---

## 本地构建 Release

```cmd
:: 单个变体 dev 模式（standalone，快速，用于本地测试）
build.bat cuda
build.bat vulkan
build.bat cpu

:: 单个变体 release（onefile，可分发）
build.bat cuda release
build.bat vulkan release
build.bat cpu release

:: 全部三种 release（顺序构建，约 30-45 min 首次，clcache 命中后更快）
build.bat all release
```

产物位置：`dist\<variant>\microagent-<variant>.exe`

---

## 触发 CI 构建（GitHub Actions）

推送版本 tag，自动并行构建三种变体并发布到 GitHub Release：

```cmd
git tag v0.2.0
git push origin v0.2.0
```

在 GitHub Actions 页面手动触发（用于测试单个变体的 CI 配置）：
Actions → Build and Release → Run workflow → 选择 variant。

---

## 项目结构

```
MicroAgent/
├── main.py                     # 入口：加载配置 → 组装 Agent → 启动 CLI
├── setup.bat                   # 开发环境搭建
├── build.bat                   # 构建入口（调度层）
├── buildscripts/
│   ├── detect-gpu.bat          # GPU 类型检测 (→ DETECTED_GPU=cuda|vulkan|cpu)
│   ├── install-vulkan-sdk.bat  # Vulkan SDK 安装（幂等）
│   ├── install-deps.bat        # 按变体安装 llama-cpp-python + 基础依赖
│   └── build-variant.bat       # Nuitka 编译逻辑
├── .github/workflows/
│   └── release.yml             # CI/CD：tag 触发，三变体并行构建
├── core/
│   ├── agent.py                # AgentRunner + ToolCallingAgent 实现
│   ├── model.py                # LlamaCppBackend + smolagents 适配
│   └── config.py               # pydantic 配置模型
├── tools/
│   ├── base.py                 # MicroTool 基类
│   ├── think.py                # ThinkTool（推理步骤展示）
│   ├── web_search.py           # DuckDuckGo / Tavily 搜索
│   ├── file_manager.py         # 文件系统操作
│   └── system_info.py          # CPU / 内存 / 电池状态
├── cli/app.py                  # CLI 交互主循环
├── ui/
│   ├── console.py              # 共享 Rich console 实例
│   └── logger.py               # 文件日志 + stderr 重定向
├── requirements-base.txt       # 通用依赖（不含 llama-cpp-python）
├── requirements.txt            # CPU 完整依赖（向后兼容）
└── requirements-dev.txt        # 开发依赖（pytest 等）
```

---

## 新增工具指南

1. 在 `tools/` 下新建 `your_tool.py`，继承 `MicroTool`
2. 在 `core/config.py` 的 `ToolsConfig` 中新增开关字段
3. 在 `tools/registry.py` 中注册该工具
4. 运行 `pytest tests/ -v` 确认无回归

---

## 运行测试

```cmd
:: 需先激活 venv
.venv\Scripts\activate.bat

:: 运行全部测试
pytest tests/ -v

:: 运行单个文件
pytest tests/test_agent.py -v
```
