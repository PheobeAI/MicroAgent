# core/loop/planner.py
from __future__ import annotations
import json
import logging
from typing import Any

from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks
from core.loop.prompt import PLANNER_SYSTEM, PLANNER_USER, format_tools
from core.loop.types import Step

_log = logging.getLogger(__name__)


class Planner:
    """Calls the model once to produce a structured execution plan."""

    def __init__(
        self,
        model: Any,
        tools: list,
        max_plan_steps: int = 10,
        show_thinking: bool = True,
    ) -> None:
        self._model = model
        self._tools = tools
        self._max_plan_steps = max_plan_steps
        self._show_thinking = show_thinking

    def plan(self, task: str) -> list[Step]:
        """Generate an execution plan for the given task.

        Returns list of Step. Retries once on parse failure.
        Raises RuntimeError if both attempts fail.
        """
        for attempt in range(2):
            raw = self._call_model(task)
            steps = self._parse(raw)
            if steps is not None:
                return steps
            _log.warning("Planner parse failure (attempt %d/2). Raw: %r", attempt + 1, raw[:200])

        raise RuntimeError("无法生成执行计划：模型连续两次未输出合法计划格式")

    def _call_model(self, task: str) -> str:
        tools_desc = format_tools(self._tools)
        system = PLANNER_SYSTEM.format(
            tools_description=tools_desc,
            max_plan_steps=self._max_plan_steps,
        )
        user = PLANNER_USER.format(task=task)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._model.generate(messages)
        content, thoughts = strip_thought_blocks(raw)
        if self._show_thinking and thoughts:
            import sys
            sys.stdout.write(f"\033[2m💭 {thoughts[0]}\033[0m\n")
            sys.stdout.flush()
        return content

    def _parse(self, content: str) -> list[Step] | None:
        result = parse_gemma_tool_call(content)
        if result is None or result["name"] != "plan":
            return None
        steps_raw = result["args"].get("steps", "")
        try:
            steps_data = json.loads(steps_raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(steps_data, list) or not steps_data:
            return None
        steps = []
        for item in steps_data:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool", "")
            args = item.get("args", {})
            reason = item.get("reason", "")
            if tool and isinstance(args, dict):
                steps.append(Step(tool=tool, args=args, reason=reason))
        return steps if steps else None
