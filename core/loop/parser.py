# core/loop/parser.py
"""Gemma native tool call parser.

Handles two formats:
  1. <|tool_call>call:NAME{key:<|"|>value<|"|>, ...}<tool_call|>
  2. Thought blocks: <|channel>thought...<channel|>  (complete or truncated)
"""
from __future__ import annotations
import re
from typing import Optional

_TOOL_CALL_RE = re.compile(
    r'<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>', re.DOTALL
)
_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)
_THOUGHT_RE = re.compile(r'<\|channel\>thought(.*?)<channel\|>', re.DOTALL)
_THOUGHT_OPEN_RE = re.compile(r'<\|channel\>thought(.*)', re.DOTALL)


def parse_gemma_tool_call(content: str) -> Optional[dict]:
    """Parse the first Gemma native tool call in content.

    Returns {"name": str, "args": dict} or None if not found.
    """
    m = _TOOL_CALL_RE.search(content)
    if not m:
        return None
    name = m.group(1)
    args_raw = m.group(2)
    args = {kv.group(1): kv.group(2) for kv in _KV_RE.finditer(args_raw)}
    return {"name": name, "args": args}


def parse_all_gemma_tool_calls(content: str) -> list[dict]:
    """Parse all Gemma native tool calls in content.

    Returns list of {"name": str, "args": dict}.
    """
    results = []
    for m in _TOOL_CALL_RE.finditer(content):
        name = m.group(1)
        args_raw = m.group(2)
        args = {kv.group(1): kv.group(2) for kv in _KV_RE.finditer(args_raw)}
        results.append({"name": name, "args": args})
    return results


def strip_thought_blocks(content: str) -> tuple[str, list[str]]:
    """Strip Gemma thought/reasoning channel blocks from content.

    Returns (stripped_content, list_of_thought_texts).
    Handles both complete blocks (<|channel>thought...<channel|>)
    and truncated blocks (opened but never closed).
    """
    thoughts: list[str] = []

    # Complete blocks
    complete = list(_THOUGHT_RE.finditer(content))
    if complete:
        for m in complete:
            thoughts.append(m.group(1).strip())
        return _THOUGHT_RE.sub("", content).strip(), thoughts

    # Truncated block
    open_m = _THOUGHT_OPEN_RE.search(content)
    if open_m:
        thoughts.append(open_m.group(1).strip())
        return _THOUGHT_OPEN_RE.sub("", content).strip(), thoughts

    return content, []
