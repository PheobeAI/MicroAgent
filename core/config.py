# core/config.py
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    path: str = "./models/gemma-4-e2b-instruct.gguf"
    n_gpu_layers: int = -1
    n_threads: int = 6
    n_ctx: int = 4096
    max_tokens: int = 512


class AgentConfig(BaseModel):
    mode: Literal["tool_calling", "code"] = "tool_calling"
    verbose: bool = False
    show_thinking: bool = True


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


class RuntimeConfig(BaseModel):
    language: str = "zh"
    log_level: str = "info"


class AppConfig(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    if config_path is None:
        import sys
        config_path = Path(sys.argv[0]).parent / "config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
