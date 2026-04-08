# tests/test_agent.py
from unittest.mock import MagicMock, patch
from core.config import AgentConfig
from core.agent import create_agent_runner


def test_tool_calling_agent_created_and_runs():
    config = AgentConfig(mode="tool_calling", verbose=False)
    mock_model = MagicMock()
    mock_tools = [MagicMock()]

    with patch("core.agent.ToolCallingAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "the answer"
        runner = create_agent_runner(config, mock_model, mock_tools)
        result = runner.run("what is 2+2?")

    mock_cls.assert_called_once_with(tools=mock_tools, model=mock_model, verbose=False)
    assert result == "the answer"


def test_code_agent_created_when_mode_is_code():
    config = AgentConfig(mode="code", verbose=True)
    mock_model = MagicMock()

    with patch("core.agent.CodeAgent") as mock_cls:
        mock_cls.return_value.run.return_value = "code result"
        runner = create_agent_runner(config, mock_model, [])
        result = runner.run("write a hello world")

    mock_cls.assert_called_once_with(tools=[], model=mock_model, verbose=True)
    assert result == "code result"
