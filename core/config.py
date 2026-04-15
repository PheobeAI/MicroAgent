# core/config.py
from pathlib import Path
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    path: str = "./models/gemma-4-e2b-instruct.gguf"
    n_gpu_layers: int = -1
    n_threads: int = 6
    n_ctx: int = 131072
    max_tokens: int = 2048


class AgentConfig(BaseModel):
    mode: Literal["plan_execute"] = "plan_execute"
    verbose: bool = False
    show_thinking: bool = True
    max_exec_rounds: int = 5
    max_plan_steps: int = 10


class WebSearchConfig(BaseModel):
    enabled: bool = True
    tavily_api_key: str = ""


class FileManagerConfig(BaseModel):
    enabled: bool = True
    allow_destructive: bool = False
    allowed_dirs: List[str] = Field(default_factory=list)


class SystemInfoConfig(BaseModel):
    enabled: bool = True


class ToolsConfig(BaseModel):
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    file_manager: FileManagerConfig = Field(default_factory=FileManagerConfig)
    system_info: SystemInfoConfig = Field(default_factory=SystemInfoConfig)


class RetrievalConfig(BaseModel):
    bm25_weight: float = 0.5
    recency_weight: float = 0.3
    importance_weight: float = 0.2
    decay_rate: float = 0.1


class MemoryConfig(BaseModel):
    enabled: bool = True
    db_path: str = r"memory\microagent.db"
    context_window_tokens: int = 131072
    compression_threshold: float = 0.80
    keep_recent_turns: int = 6
    post_compact_reserve: int = 40960
    max_episodes_in_prefix: int = 5
    pre_compact_instructions: str = ""
    max_tool_output_chars: int = 8000
    min_turns_to_save: int = 3
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


class RuntimeConfig(BaseModel):
    language: str = "zh"
    # log_level: 日志文件的记录级别，默认 info，可选 debug/info/warning/error
    log_level: str = "info"
    # console_verbose: 是否在控制台打印调试信息（smolagents 内部步骤等），默认关闭
    console_verbose: bool = False


class AppConfig(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)


def load_config(config_path: Path) -> AppConfig:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # 向后兼容：老配置写 tool_calling，自动升级为 plan_execute
        if isinstance(data.get("agent"), dict):
            if data["agent"].get("mode") == "tool_calling":
                data["agent"]["mode"] = "plan_execute"
        return AppConfig(**data)
    return AppConfig()
