"""Quick test for _repair_array_open fix."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.loop.planner import Planner


def make_planner():
    p = Planner.__new__(Planner)
    p._tools = []
    return p


def test_repair_object_written_as_array():
    """Model writes }, ["tool": ... instead of }, {"tool": ..."""
    p = make_planner()
    # The broken format seen in real model output
    broken = (
        '[{"tool": "memory_recall", "args": {}, "reason": "recall"}, '
        '["tool": "web_search", "args": {"query": "Rust"}, "reason": "search"]]'
    )
    repaired = p._repair_array_open(broken)
    data = json.loads(repaired)
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) == 2, f"Expected 2 items, got {len(data)}"
    assert data[0]["tool"] == "memory_recall"
    assert data[1]["tool"] == "web_search"
    print("PASS: repair_object_written_as_array")


def test_repair_quoted_key():
    """Model writes }, ["tool": ... (with quotes around key)."""
    p = make_planner()
    broken = (
        '[{"tool": "step1", "args": {}, "reason": "r1"}, '
        '["tool": "step2", "args": {"q": "v"}, "reason": "r2"]]'
    )
    repaired = p._repair_array_open(broken)
    data = json.loads(repaired)
    assert len(data) == 2
    assert data[1]["tool"] == "step2"
    print("PASS: repair_quoted_key")


def test_no_change_when_correct():
    """Well-formed input should not be changed."""
    p = make_planner()
    good = '[{"tool": "a", "args": {}, "reason": "r"}, {"tool": "b", "args": {}, "reason": "r2"}]'
    repaired = p._repair_array_open(good)
    assert repaired == good, f"Should not change: {repaired}"
    print("PASS: no_change_when_correct")


if __name__ == "__main__":
    test_repair_object_written_as_array()
    test_repair_quoted_key()
    test_no_change_when_correct()
    print("\nAll tests passed!")
