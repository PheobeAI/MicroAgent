# tests/test_loop/test_synthesizer.py
import pytest
from unittest.mock import MagicMock
from core.loop.synthesizer import Synthesizer
from core.loop.types import Step, Observation, SynthContext
from tools.base import Tool, ToolParam


class MockSearchTool(Tool):
    name = "web_search"
    description = "搜索"
    parameters = [ToolParam("query", "str", "词")]
    def __call__(self, **kwargs) -> str:
        return f"搜索结果: {kwargs.get('query')}"


def make_obs(result="搜索结果"):
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    return Observation(step=s, result=result, ok=True, error=None)


def test_synthesizer_plain_text_is_final_answer():
    model = MagicMock()
    model.generate = MagicMock(return_value="这是最终答案，不含工具调用")
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == "这是最终答案，不含工具调用"
    assert model.generate.call_count == 1


def test_synthesizer_tool_call_triggers_extra_round():
    tool_call = '<|tool_call>call:web_search{query:<|"|>追加搜索<|"|>}<tool_call|>'
    call_count = 0

    def side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_call
        return "最终综合答案"

    model = MagicMock()
    model.generate = MagicMock(side_effect=side_effect)
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert call_count == 2
    assert answer == "最终综合答案"


def test_synthesizer_max_rounds_forces_answer():
    model = MagicMock()
    tool_call = '<|tool_call>call:web_search{query:<|"|>一直搜索<|"|>}<tool_call|>'
    # Always return tool call → forces max_rounds fallback, then _force_answer also gets called
    model.generate = MagicMock(return_value=tool_call)
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=3)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    # After max_rounds, falls back to forced synthesis
    assert answer is not None
    assert isinstance(answer, str)


def test_synthesizer_strips_thought_before_checking():
    thought = "<|channel>thought\n我需要思考一下\n<channel|>\n"
    answer_text = "这是答案"
    model = MagicMock()
    model.generate = MagicMock(return_value=thought + answer_text)
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == answer_text
