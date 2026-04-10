# core/paths.py
import shutil
import sys
from pathlib import Path

USER_DIR: Path = Path.home() / ".pheobe" / "MicroAgent"
_SUBDIRS = ("models", "memory", "logs", "skills")

_DEFAULT_CONFIG = """\
# MicroAgent 配置文件
# 所有路径均相对于本文件所在目录

model:
  path: models\\gemma-4-e2b-instruct.gguf
  n_gpu_layers: -1
  n_threads: 6
  n_ctx: 131072
  max_tokens: 2048

agent:
  mode: tool_calling
  verbose: false
  show_thinking: true

tools:
  web_search:
    enabled: true
    tavily_api_key: ""
  file_manager:
    enabled: true
    allow_destructive: false
    allowed_dirs: []
  system_info:
    enabled: true

runtime:
  language: zh
  log_level: info
"""


def get_exe_dir() -> Path:
    """exe 所在目录；开发时为 main.py 所在目录。"""
    return Path(sys.argv[0]).resolve().parent


def resolve_relative(config_dir: Path, value: str) -> Path:
    """相对路径相对于 config_dir 解析；绝对路径直通。"""
    p = Path(value)
    if p.is_absolute():
        return p
    return (config_dir / p).resolve()


def bootstrap_user_dir(template: Path | None = None) -> Path:
    """创建 USER_DIR 目录树，写入/复制 config.yaml。返回 USER_DIR。"""
    try:
        for sub in _SUBDIRS:
            (USER_DIR / sub).mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"[ERROR] 无法创建用户目录 {USER_DIR}: {e}")
        sys.exit(1)

    config_dest = USER_DIR / "config.yaml"
    if not config_dest.exists():
        if template is not None and template.exists():
            try:
                shutil.copy(template, config_dest)
            except Exception:
                config_dest.write_text(_DEFAULT_CONFIG, encoding="utf-8")
        else:
            config_dest.write_text(_DEFAULT_CONFIG, encoding="utf-8")

    return USER_DIR


def find_config() -> Path:
    """三步查找 config.yaml；不存在时自动 bootstrap，返回 config 路径。"""
    user_config = USER_DIR / "config.yaml"
    if user_config.exists():
        return user_config

    exe_config = get_exe_dir() / "config.yaml"
    if exe_config.exists():
        return exe_config

    bootstrap_user_dir(template=exe_config)
    from ui.console import console
    console.print(f"[dim]首次运行：已在 {USER_DIR} 创建默认配置目录。"
                  f"请将 .gguf 模型文件放入 {USER_DIR / 'models'} 后再次运行。[/]")
    return USER_DIR / "config.yaml"


def log_dir() -> Path:
    """返回日志目录，不存在则创建。"""
    d = USER_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
