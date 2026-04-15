# core/loop/synthesizer.py
from __future__ import annotations
import json
import logging
from typing import Any

from core.loop.executor import Executor
from core.loop.parser import strip_thought_blocks
from core.loop.prompt import (
    SYNTHESIZER_SYSTEM, SYNTHESIZER_USER,
    format_observations, format_tools,
)
from core.loop.types import Step, Observation, SynthContext

_log = logging.getLogger(__name__)


class Synthesizer:
    """Calls the model to synthesize a final answer from observations.

    The model outputs JSON in one of two formats:
      {"type": "answer",    "text": "..."}          → return text as final answer
      {"type": "tool_call", "tool": "...", "args": {...}} → execute tool, loop

    If the model output cannot be JSON-decoded (fallback), treat as plain text answer.
    If the model outputs json_mode but type is neither, treat as answer.
    """

    def __init__(
        self,
        model: Any,
        tools: list,
        max_rounds: int = 5,
        show_thinking: bool = True,
    ) -> None:
        self._model = model
        self._tools = tools
        self._executor = Executor(tools)
        self._max_rounds = max_rounds
        self._show_thinking = show_thinking

    def synthesize(self, ctx: SynthContext, history: list[dict] | None = None, memory_prefix: str | None = None) -> str:
        observations = list(ctx.observations)
        tool_names = {t.name for t in self._tools}

        for round_num in range(self._max_rounds):
            raw = self._call_model(ctx.task, observations, round_num, history=history, memory_prefix=memory_prefix)
            content, thoughts = strip_thought_blocks(raw)
            if thoughts and self._show_thinking:
                import sys
                sys.stdout.write(f"\033[2m💭 {thoughts[0]}\033[0m\n")
                sys.stdout.flush()

            parsed = self._parse_output(content, tool_names=tool_names)

            if parsed is None:
                # Not JSON — treat as plain text final answer (safety fallback)
                _log.debug("Synthesizer: non-JSON output, treating as answer")
                return content.strip()

            action = parsed.get("action", "")

            if action == "answer":
                answer = parsed.get("text", "").strip()
                _log.info("Synthesizer produced final answer (%d chars)", len(answer))
                return answer

            if action in tool_names:
                args = parsed.get("args", {})
                _log.info("Synthesizer round %d: tool call %r args=%r", round_num + 1, action, args)
                step = Step(tool=action, args=args, reason=f"synthesizer round {round_num + 1}")
                obs = self._executor.execute(step)
                observations.append(obs)
                continue

            # Unknown action — treat as answer (model output something unexpected)
            _log.warning("Synthesizer: unknown action %r, treating as answer", action)
            return content.strip()

        _log.warning("Synthesizer exceeded max_rounds=%d, forcing final answer", self._max_rounds)
        return self._force_answer(ctx.task, observations)

    # Names of known tools — used to recognise tool-call actions
    _KNOWN_ACTIONS = {"answer"}  # extended dynamically in synthesize()

    def _parse_output(self, content: str, tool_names: set[str] | None = None) -> dict | None:
        """Try to parse content as JSON using the flat action-based schema.

        Expected formats:
          {"action": "answer",       "text": "..."}        → final answer
          {"action": "<tool_name>",  "args": {...}}         → tool call

        Returns a normalised dict with keys: action, text (optional), args (optional).
        Returns None if content is not valid JSON.
        """
        content = content.strip()
        if not content.startswith("{"):
            return None
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None

        # Normalised schema has "action" key
        if "action" in data:
            return data

        # Legacy / drift: model used "type" key (previous format)
        if "type" in data:
            t = data["type"]
            known = (tool_names or set()) | {"answer", "tool_call"}
            if t == "answer":
                return {"action": "answer", "text": data.get("text", "")}
            if t == "tool_call":
                return {"action": data.get("tool", ""), "args": data.get("args", {})}
            if t in known:
                # Model put the tool name directly in "type"
                return {"action": t, "args": data.get("args", {})}

        return None

    def _call_model(self, task: str, observations: list[Observation], round_num: int,
                    history: list[dict] | None = None, memory_prefix: str | None = None) -> str:
        tools_desc = format_tools(self._tools)
        obs_text = format_observations(observations)
        system = SYNTHESIZER_SYSTEM.format(tools_description=tools_desc)
        if memory_prefix:
            system = system + f"\n\n{memory_prefix}"
        user = SYNTHESIZER_USER.format(task=task, observations_text=obs_text)
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": user})
        return self._model.generate(messages, json_mode=True)

    def _force_answer(self, task: str, observations: list[Observation]) -> str:
        """Last resort: ask model to answer with what we have."""
        obs_text = format_observations(observations)
        system = (
            "你是回答助手。根据以下信息直接回答问题，不要调用任何工具。\n"
            '输出格式必须是 JSON：{"action": "answer", "text": "你的答案"}'
        )
        user = f"问题：{task}\n\n已收集信息：\n{obs_text}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._model.generate(messages, json_mode=True)
        content, _ = strip_thought_blocks(raw)
        parsed = self._parse_output(content.strip())
        if parsed and parsed.get("action") == "answer":
            return parsed.get("text", "").strip()
        return content.strip() or "（无法生成答案，信息不足）"
