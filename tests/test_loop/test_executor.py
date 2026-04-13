# tests/test_loop/test_executor.py
import pytest
from core.loop.executor import Executor
from core.loop.types import Step, Observation
from tools.base import Tool, ToolParam


class OkTool(Tool):
    name = "ok_tool"
    description = "成功工具"
    parameters = [ToolParam("x", "str", "输入")]
    def __call__(self, **kwargs) -> str:
        return f"结果: {kwargs.get('x', '')}"


class FailTool(Tool):
    name = "fail_tool"
    description = "总是失败"
    parameters = []
    def __call__(self, **kwargs) -> str:
        raise ValueError("工具执行失败")


def test_executor_success():
    executor = Executor(tools=[OkTool()])
    step = Step(tool="ok_tool", args={"x": "hello"}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is True
    assert obs.result == "结果: hello"
    assert obs.error is None


def test_executor_tool_raises():
    executor = Executor(tools=[FailTool()])
    step = Step(tool="fail_tool", args={}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is False
    assert "工具执行失败" in obs.error


def test_executor_unknown_tool():
    executor = Executor(tools=[OkTool()])
    step = Step(tool="nonexistent", args={}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is False
    assert "nonexistent" in obs.error


def test_executor_run_plan():
    executor = Executor(tools=[OkTool()])
    plan = [
        Step(tool="ok_tool", args={"x": "a"}, reason=""),
        Step(tool="ok_tool", args={"x": "b"}, reason=""),
    ]
    observations = executor.run_plan(plan)
    assert len(observations) == 2
    assert all(o.ok for o in observations)


def test_executor_remaps_string_args_to_first_param():
    """当模型把 args 解析成字符串时，Executor 应当将值映射到工具第一个参数。"""
    executor = Executor(tools=[OkTool()])
    # 模型输出 args:<|"|>hello<|"|> 而不是 args:{x:<|"|>hello<|"|>}
    # 导致 step.args = {"args": "hello"}
    step = Step(tool="ok_tool", args={"args": "hello"}, reason="测试")
    obs = executor.execute(step)
    assert obs.ok is True
    assert obs.result == "结果: hello"


def test_executor_run_plan_continues_on_failure():
    executor = Executor(tools=[OkTool(), FailTool()])
    plan = [
        Step(tool="fail_tool", args={}, reason=""),
        Step(tool="ok_tool", args={"x": "继续"}, reason=""),
    ]
    observations = executor.run_plan(plan)
    assert len(observations) == 2
    assert observations[0].ok is False
    assert observations[1].ok is True
