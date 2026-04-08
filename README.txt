MicroAgent v0.1.0 - 轻量本地 AI Agent
======================================

快速开始：
1. 将 .gguf 模型文件放入 models\ 目录
2. （可选）编辑 config.yaml 配置模型路径和 API Key
3. 双击运行 microagent.exe

系统要求：
- Windows 10/11 x64
- 推荐 16GB 内存
- 支持 Vulkan 的 AMD/NVIDIA GPU（可选，无 GPU 也能运行）

常见问题：
- 模型加载失败：检查 config.yaml 中 model.path 是否正确
- 搜索功能不可用：确认网络连接，或在 config.yaml 配置 tavily_api_key
- 开启文件写入：将 config.yaml 中 allow_destructive 改为 true
