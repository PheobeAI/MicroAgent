# core/loop/parser.py
"""Gemma native tool call parser.

Handles two formats:
  1. <|tool_call>call:NAME{key:<|"|>value<|"|>, ...}<tool_call|>
  2. Thought blocks: <|channel>thought...<channel|>  (complete or truncated)
"""
from __future__ import annotations
import re
from typing import Optional

# Noise tokens that may appear after the tool call closing tag
_NOISE_RE = re.compile(r'(<eos>|<\|tool_response\>|<\|eot_id\>)+')
_THOUGHT_RE = re.compile(r'<\|channel\>thought(.*?)<channel\|>', re.DOTALL)
_THOUGHT_OPEN_RE = re.compile(r'<\|channel\>thought(.*)', re.DOTALL)
_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)


def _clean_noise(content: str) -> str:
    """Remove model noise tokens from content."""
    return _NOISE_RE.sub(' ', content).strip()


def _extract_tool_call_body(content: str) -> Optional[tuple[str, str]]:
    """Extract (name, body) from a Gemma tool call.

    Handles four patterns:
      1. call:NAME{...}<tool_call|>         — normal braces with closing tag
      2. call:NAME{...} (no closing tag)    — truncated brace format
      3. call:NAME(...)<tool_call|>         — paren format with closing tag
      4. call:NAME(...) (no closing tag)    — truncated paren format

    Uses greedy matching to avoid early termination on nested structures.
    """
    # Pattern 1: braces with closing tag
    m = re.search(r'<\|tool_call\>call:(\w+)\{(.*)\}<tool_call\|>', content, re.DOTALL)
    if m:
        return m.group(1), m.group(2)

    # Pattern 3: parens with closing tag
    m = re.search(r'<\|tool_call\>call:(\w+)\((.*)\)<tool_call\|>', content, re.DOTALL)
    if m:
        return m.group(1), m.group(2)

    # Pattern 3b: parens, closing tag absent — find matching )
    m2 = re.search(r'<\|tool_call\>call:(\w+)\((.*)', content, re.DOTALL)
    if m2:
        name = m2.group(1)
        rest = m2.group(2)
        depth = 1
        end = -1
        for i, ch in enumerate(rest):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = rest[:end] if end != -1 else rest
        return name, body

    # Pattern 2: braces, closing tag absent — find matching }
    m2 = re.search(r'<\|tool_call\>call:(\w+)\{(.*)', content, re.DOTALL)
    if m2:
        name = m2.group(1)
        rest = m2.group(2)
        depth = 1
        end = -1
        for i, ch in enumerate(rest):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = rest[:end] if end != -1 else rest
        return name, body

    return None


def parse_gemma_tool_call(content: str) -> Optional[dict]:
    """Parse the first Gemma native tool call in content.

    Returns {"name": str, "args": dict} or None if not found.
    """
    content = _clean_noise(content)
    result = _extract_tool_call_body(content)
    if result is None:
        return None
    name, args_raw = result
    args = {kv.group(1): kv.group(2) for kv in _KV_RE.finditer(args_raw)}
    return {"name": name, "args": args}


def parse_all_gemma_tool_calls(content: str) -> list[dict]:
    """Parse all Gemma native tool calls in content.

    Returns list of {"name": str, "args": dict}.
    """
    content = _clean_noise(content)
    results = []
    # Find all <|tool_call>call:NAME{...}<tool_call|> blocks
    for m in re.finditer(r'<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>', content, re.DOTALL):
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
