# core/loop/synthesizer.py
from __future__ import annotations
import logging
from typing import Any

from core.loop.executor import Executor
from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks
from core.loop.prompt import (
    SYNTHESIZER_SYSTEM, SYNTHESIZER_USER,
    format_observations, format_tools,
)
from core.loop.types import Step, Observation, SynthContext

_log = logging.getLogger(__name__)


class Synthesizer:
    """Calls the model to synthesize a final answer from observations.

    If the model outputs a tool call, it executes the tool, appends the
    new observation, and calls the model again — up to max_rounds times.
    If the model outputs plain text, it is returned directly as the answer.
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

    def synthesize(self, ctx: SynthContext) -> str:
        observations = list(ctx.observations)

        for round_num in range(self._max_rounds):
            raw = self._call_model(ctx.task, observations, round_num)
            content, thoughts = strip_thought_blocks(raw)
            if thoughts:
                _log.debug("Synthesizer thought (stripped): %s", thoughts[0][:200])
                if self._show_thinking:
                    import sys
                    sys.stdout.write(f"\033[2m💭 {thoughts[0]}\033[0m\n")
                    sys.stdout.flush()

            tool_call = parse_gemma_tool_call(content)
            if tool_call is None:
                # Plain text → final answer
                answer = content.strip()
                _log.info("Synthesizer produced final answer (%d chars)", len(answer))
                return answer

            # Tool call → execute and loop
            name = tool_call["name"]
            args = tool_call["args"]
            _log.info("Synthesizer round %d: tool call %r args=%r", round_num + 1, name, args)
            step = Step(tool=name, args=args, reason=f"synthesizer round {round_num + 1}")
            obs = self._executor.execute(step)
            observations.append(obs)

        # Exceeded max_rounds — force a final answer with current observations
        _log.warning("Synthesizer exceeded max_rounds=%d, forcing final answer", self._max_rounds)
        return self._force_answer(ctx.task, observations)

    def _call_model(self, task: str, observations: list[Observation], round_num: int) -> str:
        tools_desc = format_tools(self._tools)
        obs_text = format_observations(observations)
        system = SYNTHESIZER_SYSTEM.format(tools_description=tools_desc)
        user = SYNTHESIZER_USER.format(task=task, observations_text=obs_text)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._model.generate(messages)

    def _force_answer(self, task: str, observations: list[Observation]) -> str:
        """Last resort: ask model to answer with what we have, no tool calls allowed."""
        obs_text = format_observations(observations)
        system = "你是回答助手。根据以下信息直接回答问题，不要调用任何工具，信息可能不完整。"
        user = f"问题：{task}\n\n已收集信息：\n{obs_text}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = self._model.generate(messages)
        content, _ = strip_thought_blocks(raw)
        return content.strip() or "（无法生成答案，信息不足）"
