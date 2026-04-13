# tests/test_loop/test_types.py
from core.loop.types import Step, Observation, SynthContext


def test_step_creation():
    s = Step(tool="web_search", args={"query": "中东局势"}, reason="搜索最新信息")
    assert s.tool == "web_search"
    assert s.args == {"query": "中东局势"}
    assert s.reason == "搜索最新信息"


def test_observation_success():
    s = Step(tool="web_search", args={"query": "test"}, reason="test")
    obs = Observation(step=s, result="搜索结果", ok=True, error=None)
    assert obs.ok is True
    assert obs.error is None


def test_observation_failure():
    s = Step(tool="web_search", args={"query": "test"}, reason="test")
    obs = Observation(step=s, result="", ok=False, error="网络超时")
    assert obs.ok is False
    assert obs.error == "网络超时"


def test_synth_context():
    s = Step(tool="web_search", args={}, reason="")
    obs = Observation(step=s, result="r", ok=True, error=None)
    ctx = SynthContext(task="问题", observations=[obs], round=1)
    assert ctx.round == 1
    assert len(ctx.observations) == 1
