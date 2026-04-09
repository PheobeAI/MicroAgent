# GPU 加速 + 构建基础设施设计文档

**日期：** 2026-04-09
**状态：** 已确认

---

## 1. 目标

1. **环境搭建自动化**：新设备克隆仓库后，一条命令完成开发环境搭建（Python venv、GPU 检测、正确的 llama-cpp-python 变体安装）
2. **GPU 加速**：支持 NVIDIA CUDA 和 AMD Vulkan 两种硬件加速后端
3. **多变体 Release**：本地和 CI 均可产出三种独立 exe，适配不同硬件

---

## 2. 目标硬件

| 机器 | GPU | 加速后端 | 说明 |
|---|---|---|---|
| 当前构建机 | NVIDIA 4080 | CUDA | 同时承担所有变体的构建工作 |
| 目标机 A | NVIDIA 4070 Ti Super | CUDA | 运行 microagent-cuda.exe |
| 目标机 B | AMD R7 8845H（Radeon 780M iGPU） | Vulkan | 运行 microagent-vulkan.exe；ROCm 不支持 Windows 集显 |
| 通用备用 | 无 GPU | CPU | 运行 microagent-cpu.exe |

---

## 3. 目录结构

```
MicroAgent/
├── setup.bat                        # 顶级：开发环境一键搭建
├── build.bat                        # 顶级：本地构建入口（参数: cuda|vulkan|cpu|all）
│
├── buildscripts/
│   ├── detect-gpu.bat               # 检测当前 GPU 类型，输出 DETECTED_GPU 变量
│   ├── install-vulkan-sdk.bat       # 安装 Vulkan SDK（winget，按需跳过）
│   ├── install-deps.bat             # 安装 llama-cpp-python 对应变体 + requirements-base.txt
│   └── build-variant.bat            # 运行 Nuitka，输出 microagent-<variant>.exe
│
├── .github/
│   └── workflows/
│       └── release.yml              # tag 触发，三并行 job，均调用 buildscripts/
│
├── requirements-base.txt            # 除 llama-cpp-python 外的所有运行时依赖
├── requirements.txt                 # 向后兼容：-r requirements-base.txt + llama-cpp-python（cpu）
├── requirements-dev.txt             # -r requirements-base.txt + pytest、pytest-mock
│
└── DEVELOPMENT.md                   # 开发者文档
```

**核心原则：**
- `build.bat` 和 CI yml 只是调度层，不含复杂逻辑
- `buildscripts/` 中的脚本可以在本地单独执行，方便调试
- CI 与本地构建复用同一套 `buildscripts/`

---

## 4. llama-cpp-python 三种变体安装策略

### 4.1 CUDA 变体

官方提供预编译 wheel，直接安装，**无需 CUDA Toolkit 和物理 GPU**：

```bat
pip install llama-cpp-python ^
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

运行时依赖：NVIDIA 驱动自带的 CUDA Runtime DLL。

### 4.2 Vulkan 变体

无官方预编译 wheel，必须从源码编译：

```bat
set CMAKE_ARGS=-DGGML_VULKAN=on
pip install llama-cpp-python --no-binary :all:
```

编译前置条件：
- Vulkan SDK（提供头文件和 `vulkan-1.lib`）
- VS 2022 Build Tools（C++ 编译器）
- CMake

运行时只依赖驱动自带的 `vulkan-1.dll`，无需在目标机安装 SDK。

`install-vulkan-sdk.bat` 使用 winget 安装 Vulkan SDK，安装前检测是否已存在，幂等执行。

### 4.3 CPU 变体

```bat
pip install llama-cpp-python
```

无任何额外依赖。

### 4.4 requirements 文件拆分

| 文件 | 内容 |
|---|---|
| `requirements-base.txt` | smolagents、rich、psutil、pydantic、pyyaml、ddgs、tavily-python |
| `requirements.txt` | `-r requirements-base.txt` + `llama-cpp-python`（CPU，向后兼容） |
| `requirements-dev.txt` | `-r requirements-base.txt` + pytest、pytest-mock |

`install-deps.bat <variant>` 执行顺序：
1. 按 variant 安装 llama-cpp-python
2. `pip install -r requirements-base.txt`

---

## 5. 脚本行为说明

### 5.1 setup.bat

```
用法: setup.bat [cuda|vulkan|cpu]
     （无参数时自动检测 GPU）
```

流程：
1. 检查 Python 版本（需 3.10+）
2. 创建 `.venv`（若不存在则创建）
3. 激活 `.venv`
4. 无参数时调用 `buildscripts\detect-gpu.bat` 确定变体
5. Vulkan 变体时调用 `buildscripts\install-vulkan-sdk.bat`
6. 调用 `buildscripts\install-deps.bat <variant>`
7. `pip install -r requirements-dev.txt`
8. 打印完成摘要（GPU 类型、venv 路径、运行和构建命令）

### 5.2 build.bat

```
用法: build.bat [cuda|vulkan|cpu|all] [release]
     （无参数默认: cuda dev 模式）
示例: build.bat all release   -> 顺序构建三种 release exe
      build.bat vulkan        -> Vulkan dev 模式（standalone，快）
```

流程：
- 参数 `all` → 依次调用三次 `buildscripts\build-variant.bat`
- 其他参数 → 直接调用 `buildscripts\build-variant.bat <variant> [release]`

### 5.3 buildscripts\detect-gpu.bat

检测逻辑（写入 `DETECTED_GPU` 环境变量）：
1. `nvidia-smi` 可执行 → `cuda`
2. `wmic path win32_VideoController` 含 "AMD Radeon" → `vulkan`
3. 否则 → `cpu`

### 5.4 buildscripts\install-vulkan-sdk.bat

1. 检查 `VULKAN_SDK` 环境变量是否已设置且目录存在 → 已安装则跳过
2. 调用 `winget install KhronosGroup.VulkanSDK`
3. 刷新环境变量

### 5.5 buildscripts\install-deps.bat

```
用法: install-deps.bat <cuda|vulkan|cpu>
```

按变体安装 llama-cpp-python，随后安装 `requirements-base.txt`。

### 5.6 buildscripts\build-variant.bat

```
用法: build-variant.bat <cuda|vulkan|cpu> [release]
```

从现有 `build.bat` 中提取 Nuitka 命令，输出文件名为 `microagent-<variant>.exe`，发布目录为 `dist\<variant>\`。

---

## 6. GitHub Actions 工作流

### 触发条件

- `v*` tag 推送（正式发布）
- `workflow_dispatch`（手动触发，可选择变体）

### 工作流结构

```
build-cuda   ─┐
build-vulkan  ├─ 并行 → create-release（等待全部完成）
build-cpu    ─┘
```

### 各 build job 步骤

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5 (3.12)
- uses: actions/cache@v4        # pip + clcache 缓存
- run: buildscripts\install-vulkan-sdk.bat   # 仅 vulkan job
- run: buildscripts\install-deps.bat <variant>
- run: build.bat <variant> release
- uses: actions/upload-artifact@v4
```

### 缓存策略

| 缓存 | Cache key | 效果 |
|---|---|---|
| pip 依赖 | `requirements-base.txt` hash | 跳过大部分包安装 |
| Vulkan llama-cpp-python wheel | llama-cpp-python 版本号 | 避免每次重新编译（10-15 min → <1 min） |
| Nuitka clcache | `main.py` + `core/` + `tools/` hash | 跳过 C 编译，增量构建 |

### 发布产物（GitHub Release）

```
microagent-cuda.exe      # NVIDIA GPU（CUDA 加速）
microagent-vulkan.exe    # AMD / NVIDIA GPU（Vulkan 加速）
microagent-cpu.exe       # 通用备用（纯 CPU）
config.yaml              # 示例配置
README.txt               # 用户说明
```

---

## 7. DEVELOPMENT.md 结构

```markdown
# 开发环境搭建
## 前提条件（一次性安装）
  - Python 3.10+
  - VS 2022 Build Tools（含 C++ 工作负载）
  - CMake
  - Git
## 快速开始
  - git clone → setup.bat → python main.py
## 本地构建 release
  - build.bat cuda|vulkan|cpu|all release
## 触发 CI 构建
  - git tag v0.x.x && git push --tags
## 项目结构说明
## 新增工具指南
```

---

## 8. 变更文件汇总

| 文件 | 操作 |
|---|---|
| `setup.bat` | 新建 |
| `build.bat` | 重构（改为调用 buildscripts/，保留参数接口） |
| `buildscripts/detect-gpu.bat` | 新建 |
| `buildscripts/install-vulkan-sdk.bat` | 新建 |
| `buildscripts/install-deps.bat` | 新建 |
| `buildscripts/build-variant.bat` | 新建（从 build.bat 提取 Nuitka 逻辑） |
| `.github/workflows/release.yml` | 新建 |
| `requirements-base.txt` | 新建（从 requirements.txt 拆出） |
| `requirements.txt` | 修改（改为 -r requirements-base.txt + cpu wheel） |
| `requirements-dev.txt` | 修改（改为 -r requirements-base.txt） |
| `DEVELOPMENT.md` | 新建 |
