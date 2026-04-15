# tests/test_planner_json_mode.py
"""TDD tests for JSON-mode Planner (response_format json_object).

RED phase: these tests define the NEW behavior and MUST FAIL before implementation.

New contract:
  - Planner._parse() accepts clean JSON: {"steps": [...]}
  - No native tool call wrapper required
  - No repair logic needed — llama.cpp grammar guarantees valid JSON
  - model.generate() accepts json_mode=True to enable response_format
"""
import json
import sys, os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
from core.loop.planner import Planner
from core.loop.types import Step


# ---------------------------------------------------------------------------
# Helper: make a minimal Planner with a fake model
# ---------------------------------------------------------------------------

def _make_planner(model_output: str) -> Planner:
    """Create a Planner whose model always returns model_output."""
    fake_model = MagicMock()
    fake_model.generate.return_value = model_output

    fake_tool = MagicMock()
    fake_tool.name = "web_search"
    fake_tool.describe.return_value = "web_search: search the web"

    return Planner(model=fake_model, tools=[fake_tool])


# ---------------------------------------------------------------------------
# Test 1: Planner accepts clean JSON output (new format)
# ---------------------------------------------------------------------------

def test_parse_clean_json_steps():
    """Planner._parse() should accept {"steps": [...]} without any wrapper."""
    clean_json = json.dumps({
        "steps": [
            {"tool": "web_search", "args": {"query": "Rust ownership"}, "reason": "search"}
        ]
    })
    p = _make_planner(clean_json)
    steps = p.plan("Rust 所有权是什么")
    assert len(steps) == 1
    assert steps[0].tool == "web_search"
    assert steps[0].args == {"query": "Rust ownership"}


def test_parse_clean_json_multi_step():
    """Planner._parse() should handle multiple steps in JSON mode."""
    clean_json = json.dumps({
        "steps": [
            {"tool": "web_search", "args": {"query": "q1"}, "reason": "r1"},
            {"tool": "web_search", "args": {"query": "q2"}, "reason": "r2"},
        ]
    })
    p = _make_planner(clean_json)
    steps = p.plan("multi step task")
    assert len(steps) == 2
    assert steps[0].tool == "web_search"
    assert steps[1].args == {"query": "q2"}


# ---------------------------------------------------------------------------
# Test 2: model.generate() is called with json_mode=True
# ---------------------------------------------------------------------------

def test_model_called_with_json_mode():
    """When Planner is in json_mode, generate() must be called with json_mode=True."""
    clean_json = json.dumps({
        "steps": [{"tool": "web_search", "args": {}, "reason": "r"}]
    })
    fake_model = MagicMock()
    fake_model.generate.return_value = clean_json

    fake_tool = MagicMock()
    fake_tool.name = "web_search"
    fake_tool.describe.return_value = "web_search: search"

    p = Planner(model=fake_model, tools=[fake_tool], json_mode=True)
    p.plan("task")

    # generate() must have been called with json_mode=True
    call_kwargs = fake_model.generate.call_args
    assert call_kwargs is not None
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    args = call_kwargs.args if call_kwargs.args else ()
    # json_mode could be positional or keyword
    assert kwargs.get("json_mode") is True or (len(args) > 1 and args[1] is True), \
        f"generate() not called with json_mode=True. Call args: {call_kwargs}"


# ---------------------------------------------------------------------------
# Test 3: LlamaCppBackend.generate() passes response_format when json_mode=True
# ---------------------------------------------------------------------------

def test_llamacpp_backend_json_mode():
    """LlamaCppBackend.generate() should pass response_format when json_mode=True."""
    from core.model import LlamaCppBackend, ModelConfig
    from unittest.mock import patch, MagicMock

    cfg = ModelConfig(path="fake.gguf")
    backend = LlamaCppBackend(cfg)

    # Mock the internal _llm
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"steps": []}'}}]
    }
    backend._llm = mock_llm

    backend.generate([{"role": "user", "content": "hi"}], json_mode=True)

    call_kwargs = mock_llm.create_chat_completion.call_args.kwargs
    assert call_kwargs.get("response_format") == {"type": "json_object"}, \
        f"response_format not set. kwargs: {call_kwargs}"


# ---------------------------------------------------------------------------
# Test 4: json_mode=False (default) preserves existing behavior
# ---------------------------------------------------------------------------

def test_llamacpp_backend_no_json_mode_by_default():
    """LlamaCppBackend.generate() should NOT set response_format by default."""
    from core.model import LlamaCppBackend, ModelConfig

    cfg = ModelConfig(path="fake.gguf")
    backend = LlamaCppBackend(cfg)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "hello"}}]
    }
    backend._llm = mock_llm

    backend.generate([{"role": "user", "content": "hi"}])

    call_kwargs = mock_llm.create_chat_completion.call_args.kwargs
    assert "response_format" not in call_kwargs or call_kwargs.get("response_format") is None, \
        f"response_format should not be set by default. kwargs: {call_kwargs}"
