# core/loop/executor.py
from __future__ import annotations
import logging
from typing import Any

from core.loop.types import Step, Observation

_log = logging.getLogger(__name__)


class Executor:
    """Executes tool calls from a plan, collecting Observations.

    Tool exceptions are caught and recorded as failed Observations —
    execution continues to the next step.
    """

    def __init__(self, tools: list) -> None:
        self._tools: dict[str, Any] = {t.name: t for t in tools}

    def execute(self, step: Step) -> Observation:
        """Execute a single step. Never raises — errors become Observations."""
        tool = self._tools.get(step.tool)
        if tool is None:
            err = f"未知工具: {step.tool!r}。可用工具: {list(self._tools.keys())}"
            _log.warning(err)
            return Observation(step=step, result="", ok=False, error=err)
        try:
            result = tool(**step.args)
            _log.info("Tool %r OK. Result length: %d", step.tool, len(result))
            return Observation(step=step, result=str(result), ok=True, error=None)
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            _log.warning("Tool %r raised: %s", step.tool, err)
            return Observation(step=step, result="", ok=False, error=err)

    def run_plan(self, plan: list[Step]) -> list[Observation]:
        """Execute all steps in order. Continues even if a step fails."""
        observations = []
        for step in plan:
            obs = self.execute(step)
            observations.append(obs)
        return observations
