MicroAgent - 轻量本地 AI Agent
================================

快速开始：
1. 双击运行 microagent-<variant>.exe
2. 程序自动在 C:\Users\<你的用户名>\.pheobe\MicroAgent\ 创建配置目录
3. 将 .gguf 模型文件放入该目录下的 models\ 文件夹
4. 编辑 config.yaml 中的 model.path 填写模型文件名
5. 再次运行即可使用

配置目录：C:\Users\<你的用户名>\.pheobe\MicroAgent\
  config.yaml  — 配置文件
  models\      — 模型文件
  memory\      — 记忆数据库（自动创建）
  logs\        — 运行日志（自动创建）

系统要求：
- Windows 10 / 11 x64
- 推荐 16GB 内存（模型运行期间占用约 2-4GB）
- GPU（可选）：
    microagent-cuda.exe   → NVIDIA GPU（需 CUDA 驱动）
    microagent-vulkan.exe → AMD / Intel iGPU（推荐，无需额外驱动）
    microagent-cpu.exe    → 无 GPU，纯 CPU 运行（速度较慢）

内置命令：
  /help    显示帮助
  /tools   查看已启用工具列表
  /memory  查看记忆状态与 token 占用
  /compress 立即压缩当前会话
  /clear   清空对话历史
  /config  显示当前配置

常见问题：
- 模型加载失败：检查 config.yaml 中 model.path 是否指向正确的 .gguf 文件
- 搜索功能不可用：确认网络连接；或在 config.yaml 中配置 tavily_api_key 使用更好的搜索
- 开启文件写入：将 config.yaml 中 tools.file_manager.allow_destructive 改为 true
- 响应速度慢：尝试换用 vulkan 或 cuda 变体，或在 config.yaml 降低 model.n_ctx 值

