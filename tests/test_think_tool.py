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
