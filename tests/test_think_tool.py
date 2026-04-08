# tests/test_think_tool.py
from unittest.mock import patch

from tools.think import ThinkTool


def test_forward_returns_empty_string():
    with patch("tools.think.console"):
        tool = ThinkTool(show_thinking=True)
        assert tool.forward(thought="分析当前任务的优先级") == ""


def test_forward_prints_thought_when_show_thinking_true():
    with patch("tools.think.console") as mock_console:
        tool = ThinkTool(show_thinking=True)
        tool.forward(thought="我需要先查询系统状态")
    mock_console.print.assert_called_once()
    call_arg = mock_console.print.call_args[0][0]
    assert "我需要先查询系统状态" in call_arg


def test_forward_silent_when_show_thinking_false():
    with patch("tools.think.console") as mock_console:
        tool = ThinkTool(show_thinking=False)
        tool.forward(thought="这段思考不应该显示")
    mock_console.print.assert_not_called()


def test_think_tool_metadata():
    tool = ThinkTool()
    assert tool.name == "think"
    assert tool.output_type == "string"
    assert "thought" in tool.inputs


def test_tool_calling_runner_prepends_think_tool_and_passes_instructions():
    from unittest.mock import MagicMock
    from core.config import AgentConfig
    from core.agent import create_agent_runner

    config = AgentConfig(mode="tool_calling", verbose=False, show_thinking=True)
    mock_model = MagicMock()
    mock_tool = MagicMock()

    with patch("core.agent.ToolCallingAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "ok"
        create_agent_runner(config, mock_model, [mock_tool])

    kw = mock_cls.call_args.kwargs
    assert isinstance(kw["tools"][0], ThinkTool), "ThinkTool 应在 tools 列表首位"
    assert kw["tools"][0]._show_thinking is True
    assert kw["tools"][1] is mock_tool
    assert "instructions" in kw and kw["instructions"]


def test_code_agent_runner_does_not_get_think_tool():
    from unittest.mock import MagicMock
    from core.config import AgentConfig
    from core.agent import create_agent_runner

    config = AgentConfig(mode="code", verbose=False)
    mock_model = MagicMock()
    mock_tool = MagicMock()

    with patch("core.agent.CodeAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "ok"
        create_agent_runner(config, mock_model, [mock_tool])

    passed_tools = mock_cls.call_args.kwargs["tools"]
    tool_names = [t.name for t in passed_tools if hasattr(t, "name")]
    assert "think" not in tool_names, "CodeAgentRunner 不应包含 ThinkTool"
