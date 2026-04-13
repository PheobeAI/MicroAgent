# core/agent.py
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any

from core.config import AgentConfig
from core.loop.planner import Planner
from core.loop.executor import Executor
from core.loop.synthesizer import Synthesizer
from core.loop.types import SynthContext

_log = logging.getLogger(__name__)


class AgentRunner(ABC):
    """Abstract runner — implementations define the agent loop strategy."""

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Execute a task and return the final answer."""


class PlanExecuteRunner(AgentRunner):
    """Plan-then-Execute agent loop.

    1. Planner calls the model once to produce a structured plan.
    2. Executor runs all plan steps, collecting observations.
    3. Synthesizer calls the model to produce a final answer,
       optionally requesting more tool calls (up to max_exec_rounds).
    """

    def __init__(
        self,
        model: Any,
        tools: list,
        config: AgentConfig,
        show_thinking: bool = True,
    ) -> None:
        self._model = model
        self._tools = tools
        self._config = config
        self._show_thinking = show_thinking
        self._planner = Planner(
            model=model,
            tools=tools,
            max_plan_steps=config.max_plan_steps,
            show_thinking=show_thinking,
        )
        self._executor = Executor(tools=tools)
        self._synthesizer = Synthesizer(
            model=model,
            tools=tools,
            max_rounds=config.max_exec_rounds,
            show_thinking=show_thinking,
        )

    def run(self, prompt: str) -> str:
        _log.info("PlanExecuteRunner.run: task=%r", prompt[:100])

        # Phase 1: Plan
        try:
            plan = self._planner.plan(prompt)
        except RuntimeError as e:
            _log.error("Planner failed: %s", e)
            return f"规划失败：{e}"

        _log.info("Plan: %d steps", len(plan))
        if self._config.verbose:
            for i, step in enumerate(plan, 1):
                _log.info("  Step %d: %s(%s) — %s", i, step.tool, step.args, step.reason)

        # Phase 2: Execute
        observations = self._executor.run_plan(plan)

        # Phase 3: Synthesize
        ctx = SynthContext(task=prompt, observations=observations, round=0)
        answer = self._synthesizer.synthesize(ctx)
        return answer


def create_agent_runner(
    config: AgentConfig,
    model: Any,
    tools: list,
) -> AgentRunner:
    return PlanExecuteRunner(
        model=model,
        tools=tools,
        config=config,
        show_thinking=config.show_thinking,
    )