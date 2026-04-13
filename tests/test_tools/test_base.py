# tests/test_tools/test_base.py
from tools.base import Tool, ToolParam


def test_tool_param_defaults():
    p = ToolParam(name="query", type="str", description="搜索词")
    assert p.required is True


def test_tool_describe():
    class EchoTool(Tool):
        name = "echo"
        description = "回显输入"
        parameters = [ToolParam("text", "str", "要回显的文本")]

        def __call__(self, **kwargs) -> str:
            return kwargs.get("text", "")

    t = EchoTool()
    desc = t.describe()
    assert "echo(text: str)" in desc
    assert "回显输入" in desc


def test_tool_optional_param_describe():
    class OptTool(Tool):
        name = "opt"
        description = "可选参数工具"
        parameters = [ToolParam("n", "int", "数量", required=False)]

        def __call__(self, **kwargs) -> str:
            return str(kwargs.get("n", 0))

    t = OptTool()
    assert "(可选)" in t.describe()


def test_tool_call():
    class AddTool(Tool):
        name = "add"
        description = "加法"
        parameters = [
            ToolParam("a", "int", "第一个数"),
            ToolParam("b", "int", "第二个数"),
        ]

        def __call__(self, **kwargs) -> str:
            return str(int(kwargs["a"]) + int(kwargs["b"]))

    t = AddTool()
    assert t(a=1, b=2) == "3"
