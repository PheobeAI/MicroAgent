# core/loop/planner.py
from __future__ import annotations
import json
import logging
import re
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

    # Regex to extract individual step blocks inside steps:[{...}]
    _STEP_BLOCK_RE = re.compile(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
    # Regex to parse a single KV value: key:<|"|>value<|"|>
    _STEP_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)
    # Regex to parse nested args block: args:{key:<|"|>value<|"|>, ...}
    _ARGS_BLOCK_RE = re.compile(r'args:\{([^}]*)\}', re.DOTALL)

    def _parse(self, content: str) -> list[Step] | None:
        # Strip trailing <eos> tokens emitted by some tokenizers
        content = re.sub(r'(<eos>)+\s*$', '', content).strip()

        result = parse_gemma_tool_call(content)
        if result is None or result["name"] != "plan":
            return None

        steps_raw = result["args"].get("steps", "")

        # Path A: steps value is a JSON string (ideal case)
        if steps_raw:
            try:
                steps_data = json.loads(steps_raw)
                if isinstance(steps_data, list) and steps_data:
                    return self._steps_from_json(steps_data)
            except (json.JSONDecodeError, TypeError):
                pass

        # Path B: steps value was empty (model used native KV nesting)
        # The whole steps list is embedded directly in the tool call body.
        # Raw example: steps:[{tool:<|"|>web_search<|"|>,args:{query:<|"|>x<|"|>},reason:<|"|>r<|"|>}]
        return self._parse_native_steps(content)

    def _steps_from_json(self, steps_data: list) -> list[Step] | None:
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

    def _parse_native_steps(self, content: str) -> list[Step] | None:
        """Parse steps from Gemma native KV nesting or bare JSON list format.

        Handles three formats:
          A. steps:[{tool:<|"|>NAME<|"|>, args:{k:<|"|>v<|"|>}, reason:<|"|>R<|"|>}]
             (Gemma native KV nesting — no JSON wrapping)
          B. steps:[{"tool": "NAME", "args": {"k": "v"}, "reason": "R"}]
             (bare JSON list embedded in the tool call body)
        """
        # Find the steps:[...] section — greedy to capture all content
        steps_section = re.search(r'steps:\s*(\[.*\])', content, re.DOTALL)
        if not steps_section:
            return None

        body_raw = steps_section.group(1)

        # Path B: try bare JSON list first (clean, fast)
        # Clean up stray <eos> tokens inside the JSON body before parsing
        body_clean = re.sub(r'\n?<eos>', '', body_raw).strip()
        try:
            steps_data = json.loads(body_clean)
            if isinstance(steps_data, list) and steps_data:
                return self._steps_from_json(steps_data)
        except (json.JSONDecodeError, TypeError):
            pass

        # Path A: Gemma native KV nesting
        steps = []
        for block_m in self._STEP_BLOCK_RE.finditer(body_raw):
            block = block_m.group(0)

            top_kvs = {m.group(1): m.group(2) for m in self._STEP_KV_RE.finditer(block)}
            tool_name = top_kvs.get("tool", "")
            reason = top_kvs.get("reason", "")

            args: dict = {}
            args_m = self._ARGS_BLOCK_RE.search(block)
            if args_m:
                args = {m.group(1): m.group(2) for m in self._STEP_KV_RE.finditer(args_m.group(1))}

            if tool_name:
                steps.append(Step(tool=tool_name, args=args, reason=reason))

        return steps if steps else None
