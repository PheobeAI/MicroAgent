# tests/test_config.py
from pathlib import Path
import pytest
from core.config import load_config, AppConfig


def test_defaults_when_file_missing():
    config = load_config(Path("/nonexistent/config.yaml"))
    assert isinstance(config, AppConfig)
    assert config.model.n_threads == 6
    assert config.model.n_gpu_layers == -1
    assert config.model.n_ctx == 131072
    assert config.model.max_tokens == 2048
    assert config.agent.mode == "tool_calling"
    assert config.agent.verbose is False
    assert config.agent.show_thinking is True
    assert config.tools.file_manager.allow_destructive is False
    assert config.tools.file_manager.allowed_dirs == []
    assert config.tools.web_search.tavily_api_key == ""
    assert config.runtime.language == "zh"


def test_yaml_overrides_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model:\n  n_threads: 4\nagent:\n  verbose: false\n", encoding="utf-8")
    config = load_config(cfg)
    assert config.model.n_threads == 4
    assert config.agent.verbose is False
    assert config.model.n_gpu_layers == -1  # default preserved


def test_invalid_agent_mode_raises(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("agent:\n  mode: unknown_mode\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(cfg)


def test_allowed_dirs_parsed(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "tools:\n  file_manager:\n    allow_destructive: true\n    allowed_dirs:\n      - /tmp\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.tools.file_manager.allow_destructive is True
    assert config.tools.file_manager.allowed_dirs == ["/tmp"]
