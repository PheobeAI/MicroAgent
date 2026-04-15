# tests/test_loop/test_synthesizer.py
import json
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


# 新格式：action 字段，值是 "answer" 或工具名
def json_answer(text: str) -> str:
    return json.dumps({"action": "answer", "text": text}, ensure_ascii=False)


def json_tool_call(tool: str, args: dict) -> str:
    return json.dumps({"action": tool, "args": args}, ensure_ascii=False)


# ── 核心格式测试 ──────────────────────────────────────────────────────────────

def test_synthesizer_json_answer_returned_as_text():
    """{"action": "answer", "text": "..."} → 直接返回 text 内容。"""
    model = MagicMock()
    model.generate = MagicMock(return_value=json_answer("这是最终答案"))
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == "这是最终答案"
    assert model.generate.call_count == 1


def test_synthesizer_json_tool_call_triggers_extra_round():
    """{"action": "web_search", "args": {...}} → 执行工具，再调模型。"""
    call_count = 0

    def side_effect(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json_tool_call("web_search", {"query": "追加搜索"})
        return json_answer("最终综合答案")

    model = MagicMock()
    model.generate = MagicMock(side_effect=side_effect)
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert call_count == 2
    assert answer == "最终综合答案"


def test_synthesizer_model_called_with_json_mode():
    """Synthesizer 应以 json_mode=True 调用 model.generate()。"""
    model = MagicMock()
    model.generate = MagicMock(return_value=json_answer("答案"))
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    synth.synthesize(ctx)

    call_kwargs = model.generate.call_args.kwargs
    assert call_kwargs.get("json_mode") is True, \
        f"generate() not called with json_mode=True: {model.generate.call_args}"


def test_synthesizer_max_rounds_forces_answer():
    """超过 max_rounds 时强制生成答案，不崩溃。"""
    model = MagicMock()
    model.generate = MagicMock(return_value=json_tool_call("web_search", {"query": "一直搜索"}))
    synth = Synthesizer(model=model, tools=[MockSearchTool()], max_rounds=3)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer is not None
    assert isinstance(answer, str)


def test_synthesizer_plain_text_fallback():
    """如果模型输出无法 json.loads（纯文本），直接当做答案返回。"""
    model = MagicMock()
    model.generate = MagicMock(return_value="这是纯文本答案，没有 JSON 包装")
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == "这是纯文本答案，没有 JSON 包装"


def test_synthesizer_strips_thought_before_checking():
    """thought 块应在解析前剥离，不影响 JSON 解析。"""
    thought = "<|channel>thought\n我需要思考一下\n<channel|>\n"
    model = MagicMock()
    model.generate = MagicMock(return_value=thought + json_answer("这是答案"))
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    answer = synth.synthesize(ctx)
    assert answer == "这是答案"


def test_synthesizer_memory_prefix_injected_into_system():
    """memory_prefix 应追加到 system prompt，出现在传给模型的第一条消息中。"""
    captured_messages = []

    def capture(messages, **kwargs):
        captured_messages.extend(messages)
        return json_answer("最终答案")

    model = MagicMock()
    model.generate = MagicMock(side_effect=capture)
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    synth.synthesize(ctx, memory_prefix="[记忆]\n## 已知事实\n- lang: zh\n[/记忆]")

    system_msg = captured_messages[0]
    assert system_msg["role"] == "system"
    assert "[记忆]" in system_msg["content"]
    assert "lang: zh" in system_msg["content"]


def test_synthesizer_no_memory_prefix_no_injection():
    """不传 memory_prefix 时，system prompt 中不应含 [记忆] 标记。"""
    captured_messages = []

    def capture(messages, **kwargs):
        captured_messages.extend(messages)
        return json_answer("答案")

    model = MagicMock()
    model.generate = MagicMock(side_effect=capture)
    synth = Synthesizer(model=model, tools=[], max_rounds=5)
    ctx = SynthContext(task="问题", observations=[make_obs()], round=0)
    synth.synthesize(ctx)

    system_msg = captured_messages[0]
    assert "[记忆]" not in system_msg["content"]