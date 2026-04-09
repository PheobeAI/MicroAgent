# 需求文档：轻量化本地 AI Agent 运行环境

## 1. 项目目标
构建一个极致轻量的本地 AI Agent 解决方案，要求在 **AMD R7 8845H (16G RAM)** 轻薄本上流畅运行。该 Agent 需具备工具调用（Tool Use）能力，且能打包成独立运行的二进制文件（.exe）。

## 2. 技术栈约束 (Technical Stack)
* **Agent 框架:** `smolagents` (Hugging Face 出品，因其极致轻量且基于代码解释器模式)。
* **推理后端:** `llama-cpp-python` (支持 GGUF 格式，易于打包)。
* **首选模型:** `Gemma-4-E2B-Instruct` (或同级别 2B 规模移动端优化模型)。
* **硬件加速:** 必须配置 `Vulkan` 或 `OpenCL` 后端以利用 **AMD Radeon 780M iGPU**。
* **打包工具:** `Nuitka` (推荐，性能比 PyInstaller 更好且生成的 exe 更难被反编译)。

## 3. 核心功能需求

### 3.1 本地模型加载
* 支持从指定路径加载本地 `.gguf` 格式模型。
* **内存管理:** 针对 16G 内存进行优化，模型加载后显存/内存占用需控制在 4GB 以内。
* **线程控制:** 限制 CPU 线程使用数（建议 4-6 线程），确保不影响系统其他任务。

### 3.2 技能与工具系统 (Skill/Tooling)
* 实现一个简单的 `Tool` 类，允许 Agent 通过自然语言触发 Python 函数。
* **示例工具清单 (MVP):**
    * `web_search`: 使用简单接口搜索网页。
    * `file_manager`: 读取本地文本文件或保存结果。
    * `system_info`: 获取当前 CPU、内存、电池状态。

### 3.3 交互界面
* **初期阶段:** 提供带彩色输出的命令行界面 (CLI)。
* **交互逻辑:** 输入自然语言指令 -> Agent 规划步骤 -> 调用 Tool -> 输出最终答案。

## 4. 打包与分发需求
* **零依赖:** 打包后的 `.exe` 必须内置 Python 运行时。
* **模型外置/内置可选:** 支持将模型文件放在 exe 同级目录，或在启动时检查。
* **静态资源优化:** 剔除不必要的库，减小 exe 体积。

## 5. 针对 R7 8845H 的性能优化建议 (给 Claude 的开发指令)
> "Please optimize the `llama-cpp-python` installation flags for **AMD AVX-512** and **Vulkan**. Ensure that the Agent logic defaults to `n_gpu_layers=-1` to offload all possible layers to the Radeon 780M iGPU. Implement a basic prompt template that is compatible with Gemma-4's instruction format."

## 6. 交付物要求
1.  **main.py**: 核心 Agent 逻辑代码。
2.  **tools.py**: 工具定义函数。
3.  **requirements.txt**: 最小化依赖清单。
4.  **build_script.ps1**: 用于 Nuitka 打包的 PowerShell 脚本。
