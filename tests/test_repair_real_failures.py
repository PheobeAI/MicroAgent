"""Tests for real failure patterns from integration test logs."""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.loop.planner import Planner

p = Planner.__new__(Planner)
p._tools = []

CASES = {
    # Pattern from 第3轮/第7轮: step outside array (], \n{...} pattern)
    "outside_array": (
        '[{"tool": "memory_recall", "args": {}, "reason": "recall"},\n'
        '{"tool": "web_search", "args": {"query": "Rust ownership"}, "reason": "search"}]'
    ),
    # Same but with ], { (closing bracket then object)
    "outside_array_bracket_comma": (
        '[{"tool": "memory_recall", "args": {}, "reason": "recall"}],\n'
        '{"tool": "web_search", "args": {"query": "Rust GIL"}, "reason": "search"}'
    ),
    # Pattern from 第5轮: reason leaked outside args object
    # {"tool": "memory_store", "args": {"key": "...", "value": "..."}, "reason": "..."}]
    # (This is actually valid JSON — the failure was something else in the raw)
    # The real failure was: args {...}, "reason": "..."} where args closed too early
    "reason_outside_args": (
        '[{"tool": "memory_store", "args": {"key": "user_preference", "value": "中文"}, '
        '"reason": "save pref"}]'
    ),
    # Pattern: }, ["tool": "name", ... (object written with [ opener)
    "array_open_with_tool_key": (
        '[{"tool": "memory_recall", "args": {}, "reason": "r1"}, '
        '["tool": "web_search", "args": {"query": "q"}, "reason": "r2"]]'
    ),
    # Pattern: }, ["name", "args": ... (orphan tool name, no key)
    "array_open_orphan_name": (
        '[{"tool": "memory_recall", "args": {}, "reason": "r1"}, '
        '["web_search", "args": {"query": "q"}, "reason": "r2"]]'
    ),
}

all_pass = True
for name, broken in CASES.items():
    # Try direct parse first
    try:
        data = json.loads(broken)
        tools = [x.get("tool") for x in data if isinstance(x, dict)]
        print(f"ALREADY_VALID ({name}): {tools}")
        continue
    except json.JSONDecodeError:
        pass
    # Apply repair
    repaired = p._repair_steps_json(broken)
    try:
        data = json.loads(repaired)
        tools = [x.get("tool") for x in data if isinstance(x, dict)]
        if tools and all(tools):
            print(f"PASS ({name}): {tools}")
        else:
            print(f"FAIL ({name}): parsed but missing tools: {data}")
            all_pass = False
    except Exception as e:
        print(f"FAIL ({name}): {e}")
        print(f"  repaired: {repaired[:150]}")
        all_pass = False

print()
print("All passed!" if all_pass else "SOME TESTS FAILED")
