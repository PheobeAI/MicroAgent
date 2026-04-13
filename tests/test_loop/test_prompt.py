# tests/test_loop/test_prompt.py
from core.loop.prompt import format_observations, format_tools
from core.loop.types import Step, Observation
from tools.base import Tool, ToolParam


class DummyTool(Tool):
    name = "dummy"
    description = "测试工具"
    parameters = [ToolParam("x", "str", "输入")]

    def __call__(self, **kwargs) -> str:
        return ""


def test_format_tools():
    t = DummyTool()
    result = format_tools([t])
    assert "dummy(x: str)" in result
    assert "测试工具" in result


def test_format_observations_success():
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    obs = Observation(step=s, result="搜索结果内容", ok=True, error=None)
    text = format_observations([obs])
    assert "✓" in text
    assert "web_search" in text
    assert "搜索结果内容" in text


def test_format_observations_failure():
    s = Step(tool="web_search", args={"query": "test"}, reason="")
    obs = Observation(step=s, result="", ok=False, error="超时")
    text = format_observations([obs])
    assert "✗" in text
    assert "超时" in text
