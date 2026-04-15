"""Tests for real-world model output patterns."""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.loop.planner import Planner

p = Planner.__new__(Planner)
p._tools = []

# Real pattern from failure log (attempt 1):
# }, ["web_search", "args": {"query": ...}  -- no "tool": prefix
broken_real1 = (
    '[{"tool": "memory_recall", "args": {}, "reason": "recall"}, '
    '["web_search", "args": {"query": "Rust ownership"}, "reason": "search"]]'
)

# Real pattern from failure log (attempt 2):
# }, ["tool": "web_search", ...  -- has "tool": prefix
broken_real2 = (
    '[{"tool": "memory_recall", "args": {}, "reason": "recall"}, '
    '["tool": "web_search", "args": {"query": "Rust"}, "reason": "search"]]'
)

print("=== Pattern 1: no 'tool:' prefix (tuple-like) ===")
repaired1 = p._repair_array_open(broken_real1)
print("Repaired:", repaired1[:150])
try:
    d = json.loads(repaired1)
    print("Parse OK:", [x.get("tool") for x in d])
except Exception as e:
    print("Parse FAIL:", e)

print()
print("=== Pattern 2: with 'tool:' prefix ===")
repaired2 = p._repair_array_open(broken_real2)
print("Repaired:", repaired2[:150])
try:
    d = json.loads(repaired2)
    print("Parse OK:", [x.get("tool") for x in d])
except Exception as e:
    print("Parse FAIL:", e)
