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

try:
    from smolagents.monitoring import LogLevel
except ImportError:
    LogLevel = None  # type: ignore


def _verbosity(verbose: bool) -> Any:
    """Map bool verbose flag to smolagents LogLevel."""
    if LogLevel is None:
        return verbose  # fallback for very old versions
    return LogLevel.DEBUG if verbose else LogLevel.ERROR


_INSTRUCTIONS = (
    "每次回复都必须调用一个工具。"
    "当你已经得出最终答案，或者已经收集到足够信息时，"
    "必须立即调用 final_answer(answer=\"...\") 工具来提交结果，不要再继续搜索或思考。"
    "禁止输出不带工具调用的纯文本，否则系统将报错并重试。"
)


class AgentRunner(ABC):
    """Abstract runner — swap to change agent strategy (tool_calling vs code)."""

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Execute a task and return the final answer."""


class ToolCallingAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool, show_thinking: bool) -> None:
        # ThinkTool has been removed: Gemma uses its native <|channel>thought...<channel|>
        # reasoning blocks for internal reasoning. The model wrapper (_LlamaCppSmolagentsModel)
        # strips these blocks and optionally displays them based on show_thinking config.
        self._agent = ToolCallingAgent(
            tools=list(tools),
            model=model,
            verbosity_level=_verbosity(verbose),
            instructions=_INSTRUCTIONS,
        )

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


class CodeAgentRunner(AgentRunner):
    def __init__(self, model: Any, tools: List[Any], verbose: bool) -> None:
        self._agent = CodeAgent(
            tools=tools, model=model, verbosity_level=_verbosity(verbose)
        )

    def run(self, prompt: str) -> str:
        return self._agent.run(prompt)


def create_agent_runner(
    config: AgentConfig, model: Any, tools: List[Any]
) -> AgentRunner:
    if config.mode == "tool_calling":
        return ToolCallingAgentRunner(
            model, tools,
            verbose=config.verbose,
            show_thinking=config.show_thinking,
        )
    if config.mode == "code":
        return CodeAgentRunner(model, tools, verbose=config.verbose)
    raise ValueError(f"Unknown agent mode: {config.mode!r}")
