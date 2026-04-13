# tests/test_loop/test_planner.py
import json
import pytest
from unittest.mock import MagicMock
from core.loop.planner import Planner
from core.loop.types import Step
from tools.base import Tool, ToolParam


class MockSearchTool(Tool):
    name = "web_search"
    description = "搜索网络"
    parameters = [ToolParam("query", "str", "搜索词")]
    def __call__(self, **kwargs) -> str: return ""


def make_model(raw_output: str):
    model = MagicMock()
    model.generate = MagicMock(return_value=raw_output)
    return model


def gemma_plan(steps: list) -> str:
    steps_json = json.dumps(steps, ensure_ascii=False)
    return f'<|tool_call>call:plan{{steps:<|"|>{steps_json}<|"|>}}<tool_call|>'


def test_planner_returns_steps():
    raw = gemma_plan([
        {"tool": "web_search", "args": {"query": "中东"}, "reason": "搜索"},
    ])
    model = make_model(raw)
    tools = [MockSearchTool()]
    planner = Planner(model=model, tools=tools, max_plan_steps=10)
    plan = planner.plan("预测中东局势")
    assert len(plan) == 1
    assert isinstance(plan[0], Step)
    assert plan[0].tool == "web_search"
    assert plan[0].args == {"query": "中东"}


def test_planner_multiple_steps():
    raw = gemma_plan([
        {"tool": "web_search", "args": {"query": "A"}, "reason": "第一步"},
        {"tool": "web_search", "args": {"query": "B"}, "reason": "第二步"},
    ])
    planner = Planner(model=make_model(raw), tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert len(plan) == 2


def test_planner_retry_on_parse_failure():
    good_raw = gemma_plan([{"tool": "web_search", "args": {"query": "x"}, "reason": "r"}])
    call_count = 0

    def side_effect(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "无效输出"
        return good_raw

    model = MagicMock()
    model.generate = MagicMock(side_effect=side_effect)
    planner = Planner(model=model, tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert call_count == 2
    assert len(plan) == 1


def test_planner_raises_after_two_failures():
    model = make_model("无效输出，无法解析")
    planner = Planner(model=model, tools=[MockSearchTool()], max_plan_steps=10)
    with pytest.raises(RuntimeError, match="无法生成执行计划"):
        planner.plan("任务")


def test_planner_native_kv_steps_format():
    """模型实际输出：steps 值也是 Gemma native KV 嵌套格式，而不是 JSON 字符串。"""
    raw = (
        '<|tool_call>call:plan{steps:[{'
        'tool:<|"|>web_search<|"|>,'
        'args:{query:<|"|>中东局势进展<|"|>},'
        'reason:<|"|>需要搜索最新信息<|"|>'
        '}]}<tool_call|>'
    )
    planner = Planner(model=make_model(raw), tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert len(plan) == 1
    assert plan[0].tool == "web_search"
    assert plan[0].args == {"query": "中东局势进展"}
    assert "搜索" in plan[0].reason


def test_planner_native_kv_strips_eos():
    """模型输出末尾有 <eos> token，应当正常解析。"""
    raw = (
        '<|tool_call>call:plan{steps:[{'
        'tool:<|"|>web_search<|"|>,'
        'args:{query:<|"|>test<|"|>},'
        'reason:<|"|>r<|"|>'
        '}]}<tool_call|><eos><eos><eos>'
    )
    planner = Planner(model=make_model(raw), tools=[MockSearchTool()], max_plan_steps=10)
    plan = planner.plan("任务")
    assert len(plan) == 1
    assert plan[0].tool == "web_search"
