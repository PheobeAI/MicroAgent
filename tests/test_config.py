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
    assert config.agent.mode == "plan_execute"
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


def test_memory_config_defaults():
    config = load_config(Path("/nonexistent/config.yaml"))
    m = config.memory
    assert m.enabled is True
    assert m.db_path == r"memory\microagent.db"
    assert m.context_window_tokens == 131072
    assert m.compression_threshold == 0.80
    assert m.keep_recent_turns == 6
    assert m.post_compact_reserve == 40960
    assert m.max_episodes_in_prefix == 5
    assert m.pre_compact_instructions == ""
    assert m.max_tool_output_chars == 8000
    assert m.min_turns_to_save == 3
    assert m.retrieval.bm25_weight == 0.5
    assert m.retrieval.recency_weight == 0.3
    assert m.retrieval.importance_weight == 0.2
    assert m.retrieval.decay_rate == 0.1


def test_memory_config_yaml_override(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "memory:\n  enabled: false\n  max_episodes_in_prefix: 0\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.memory.enabled is False
    assert config.memory.max_episodes_in_prefix == 0
    assert config.memory.compression_threshold == 0.80  # default preserved
