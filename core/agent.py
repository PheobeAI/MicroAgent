# core/agent.py
from abc import ABC, abstractmethod
from typing import Any, List

from core.config import AgentConfig

try:
    from smolagents import ToolCallingAgent
except ImportError:
    ToolCallingAgent = None  # type: ignore

try:
    from smolagents import CodeAgent
except ImportError:
    CodeAgent = None  # type: ignore


class AgentRunner(ABC):
    """Abstract runner — swap to change agent strategy (tool_calling vs code)."""

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Execute a task and return the final answer."""


class ToolCallingAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool) -> None:
        self._agent = ToolCallingAgent(tools=tools, model=model, verbose=verbose)

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


class CodeAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool) -> None:
        self._agent = CodeAgent(tools=tools, model=model, verbose=verbose)

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


def create_agent_runner(
    config: AgentConfig, model: Any, tools: List[Any]
) -> AgentRunner:
    if config.mode == "tool_calling":
        return ToolCallingAgentRunner(model, tools, verbose=config.verbose)
    if config.mode == "code":
        return CodeAgentRunner(model, tools, verbose=config.verbose)
    raise ValueError(f"Unknown agent mode: {config.mode!r}")
