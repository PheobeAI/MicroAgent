# core/loop/planner.py
from __future__ import annotations
import json
import logging
import re
from typing import Any

from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks
from core.loop.prompt import PLANNER_SYSTEM, PLANNER_USER, format_tools
from core.loop.types import Step

_log = logging.getLogger(__name__)


class Planner:
    """Calls the model once to produce a structured execution plan."""

    def __init__(
        self,
        model: Any,
        tools: list,
        max_plan_steps: int = 10,
        show_thinking: bool = True,
        json_mode: bool = True,
    ) -> None:
        self._model = model
        self._tools = tools
        self._max_plan_steps = max_plan_steps
        self._show_thinking = show_thinking
        self._json_mode = json_mode

    def plan(self, task: str, history: list[dict] | None = None, memory_prefix: str | None = None) -> list[Step]:
        """Generate an execution plan for the given task.

        Returns list of Step. Retries once on parse failure.
        Raises RuntimeError if both attempts fail.
        """
        for attempt in range(2):
            raw = self._call_model(task, history=history, memory_prefix=memory_prefix)
            steps = self._parse(raw)
            if steps is not None:
                return steps
            _log.warning("Planner parse failure (attempt %d/2). Raw: %r", attempt + 1, raw[:200])

        raise RuntimeError("无法生成执行计划：模型连续两次未输出合法计划格式")

    def _call_model(self, task: str, history: list[dict] | None = None, memory_prefix: str | None = None) -> str:
        tools_desc = format_tools(self._tools)

        # 将历史摘要注入 task 描述，而非插入消息列表
        # 插入消息列表会让模型进入"对话模式"，破坏 plan 格式输出
        task_with_ctx = task
        if history:
            recent = history[-6:]  # 最近 3 轮（user+assistant 各一条）
            ctx_lines = []
            for msg in recent:
                role = msg.get("role", "")
                content = str(msg.get("content", ""))[:300]
                if role == "user":
                    ctx_lines.append(f"[上文用户]: {content}")
                elif role == "assistant":
                    ctx_lines.append(f"[上文回答]: {content}")
            if ctx_lines:
                ctx_str = "\n".join(ctx_lines)
                task_with_ctx = f"【对话背景】\n{ctx_str}\n\n【当前任务】\n{task}"

        system = PLANNER_SYSTEM.format(
            tools_description=tools_desc,
            max_plan_steps=self._max_plan_steps,
        )
        # 记忆前缀追加到 system prompt 末尾
        if memory_prefix:
            system = system + f"\n\n{memory_prefix}"

        user = PLANNER_USER.format(task=task_with_ctx)
        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": user})
        raw = self._model.generate(messages, json_mode=self._json_mode)
        content, thoughts = strip_thought_blocks(raw)
        if self._show_thinking and thoughts:
            import sys
            sys.stdout.write(f"\033[2m💭 {thoughts[0]}\033[0m\n")
            sys.stdout.flush()
        return content

    # Regex to extract individual step blocks inside steps:[{...}]
    _STEP_BLOCK_RE = re.compile(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
    # Regex to parse a single KV value: key:<|"|>value<|"|>
    _STEP_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)
    # Regex to parse nested args block: args:{key:<|"|>value<|"|>, ...}  (native KV)
    _ARGS_BLOCK_RE = re.compile(r'args:\{([^}]*)\}', re.DOTALL)
    # Regex to parse args as JSON object: args:{"key": "value", ...}
    _ARGS_JSON_RE = re.compile(r'args:(\{[^{}]*\})', re.DOTALL)

    # Repair pattern: model writes [..., ["tool": ... instead of {..., {"tool": ...
    _ARRAY_OBJ_ITEM_RE = re.compile(r'},\s*(\[)', re.DOTALL)

    # Matches orphan tool-name value: "tool_name", "key": (first item is a bare string, not a KV)
    _ORPHAN_TOOL_NAME_RE = re.compile(r'^\s*"(\w+)",\s*"(?!tool")')

    def _repair_steps_json(self, text: str) -> str:
        """Apply all known repair passes to a broken steps JSON string.

        Known failure patterns from real model output:
          1. [{...}],\\n{...}   — step placed outside the closed array   → re-insert + close
          2. [{...}], [{...}]   — two separate arrays                    → merge
          3. [{...}, ["tool":   — object written with [ opener            → fix brackets
          4. [{...}, ["name",   — orphan tool name (no "tool": key)      → fix brackets + inject key
          5. trailing noise     — stray KV after closing ]               → strip
        """
        repaired = text
        # Repair 1: [{...}], \n{...}  (a second object AFTER the closing ])
        # Strategy: remove the ] before the stray object, and add ] at the very end.
        # This handles: [{...}],\n{...}  →  [{...}, {...}]
        repaired = re.sub(
            r'\]\s*,\s*(\{[^[\]]*\})\s*$',
            r', \1]',
            repaired,
            flags=re.DOTALL,
        )
        # Repair 2: [...], [...] → [..., ...]
        repaired = re.sub(r'\]\s*,\s*\[', ',', repaired)
        # Repair 3+4: }, [ used instead of }, {
        repaired = self._repair_array_open(repaired)
        # Strip trailing noise after closing ]
        repaired = re.sub(r'\]\s*,\s*"?\w+"?\s*:.*$', ']', repaired, flags=re.DOTALL)
        return repaired

    def _repair_array_open(self, text: str) -> str:
        """Replace }, [...] with }, {...} when [ is used as an object-open (format drift).

        The model sometimes writes:
          [{"tool": "a", ...}, ["tool": "b", ...]]        -- variant A: has "tool": key
          [{"tool": "a", ...}, ["b", "args": {...}, ...]] -- variant B: tool name is first bare value

        We find each }, [ occurrence and match brackets to replace [...]→{...}.
        For variant B, we also inject "tool": before the orphan tool name.
        """
        result = list(text)
        # Process in reverse to preserve positions during multi-pass replacement
        for m in reversed(list(self._ARRAY_OBJ_ITEM_RE.finditer(text))):
            bracket_pos = m.start(1)
            # Find matching ] by counting bracket depth
            depth = 0
            close_pos = -1
            for i in range(bracket_pos, len(text)):
                if text[i] == '[':
                    depth += 1
                elif text[i] == ']':
                    depth -= 1
                    if depth == 0:
                        close_pos = i
                        break
            if close_pos == -1:
                continue  # unmatched bracket — skip
            inner = text[bracket_pos + 1:close_pos]
            # Variant A: inner already has "key": pattern — just swap [ → { and ] → }
            if re.search(r'"?\w+"?\s*:', inner):
                result[bracket_pos] = '{'
                result[close_pos] = '}'
                # Variant B sub-case: first item is orphan tool name "name", "key":...
                # Convert: {"name", "args": ... } → {"tool": "name", "args": ...}
                orphan_m = self._ORPHAN_TOOL_NAME_RE.match(inner)
                if orphan_m:
                    # We need to insert "tool": before the first quote after {
                    # This requires string surgery — rebuild this section
                    # Find position of first " inside the bracket
                    first_quote = None
                    for j in range(bracket_pos + 1, close_pos):
                        if result[j] == '"':
                            first_quote = j
                            break
                    if first_quote is not None:
                        result.insert(first_quote, '"tool": ')
        return ''.join(result)

    def _parse(self, content: str) -> list[Step] | None:
        # Strip noise tokens
        content = re.sub(r'(<eos>|<\|tool_response\>)+\s*$', '', content).strip()
        content = re.sub(r'(<eos>|<\|tool_response\>)+', ' ', content).strip()

        # Priority Path: JSON mode — model outputs {"steps": [...]} directly
        # llama.cpp grammar sampling guarantees valid JSON, so no repair needed.
        if self._json_mode:
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "steps" in data:
                    steps_data = data["steps"]
                    if isinstance(steps_data, list) and steps_data:
                        parsed = self._steps_from_json(steps_data)
                        if parsed:
                            return parsed
            except (json.JSONDecodeError, TypeError):
                # JSON mode but output was not valid JSON (e.g. model noise)
                # Fall through to legacy native format parsers as safety net
                _log.debug("JSON mode parse failed, falling back to native format parsers")

        # Case C: model skipped plan format, directly output a tool call
        # e.g. <|tool_call>call:memory_recall{...}<tool_call|>
        # Treat it as a single-step plan.
        result = parse_gemma_tool_call(content)
        if result is not None and result["name"] != "plan":
            tool_name = result["name"]
            args = result["args"]
            if tool_name and any(tool_name == t.name for t in self._tools):
                _log.info("Planner: model skipped plan, wrapping direct tool call '%s' as single step", tool_name)
                return [Step(tool=tool_name, args=args, reason="(direct tool call)")]

        if result is None:
            return None

        if result["name"] != "plan":
            return None

        steps_raw = result["args"].get("steps", "")

        # Path A: steps value parsed by _KV_RE (ideal case — has closing <|"|>)
        if steps_raw:
            try:
                steps_data = json.loads(steps_raw)
                if isinstance(steps_data, list) and steps_data:
                    return self._steps_from_json(steps_data)
            except (json.JSONDecodeError, TypeError):
                repaired = self._repair_steps_json(steps_raw)
                try:
                    steps_data = json.loads(repaired)
                    if isinstance(steps_data, list) and steps_data:
                        return self._steps_from_json(steps_data)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Path B: steps value empty — model omitted closing <|"|>, try to
        # extract steps:[...] from the raw body using native steps parser.
        # Also handles broken multi-array format: [...], [...]
        steps_via_native = self._parse_native_steps(content)
        if steps_via_native:
            return steps_via_native

        # Path C: last resort — extract steps value after <|"|> without closing tag
        # e.g. steps:<|"|>[{"tool":"x",...}]  (no closing <|"|>)
        steps_open = re.search(r'steps:<\|"\|>(\[.*)', content, re.DOTALL)
        if steps_open:
            raw_steps = steps_open.group(1).strip()
            # Truncate trailing noise: everything from the first noise token OR
            # stray } after the closing ] (e.g. ]}<tool_call|>)
            raw_steps = re.sub(r'(<eos>|<\|tool_response\>|<tool_call\|>|<\|"\|>).*$', '', raw_steps, flags=re.DOTALL).strip()
            # Remove stray } that may follow the JSON array closing ]
            raw_steps = re.sub(r'\]\s*\}.*$', ']', raw_steps, flags=re.DOTALL).strip()
            try:
                steps_data = json.loads(raw_steps)
                if isinstance(steps_data, list) and steps_data:
                    return self._steps_from_json(steps_data)
            except (json.JSONDecodeError, TypeError):
                # Repair 1: [...], [...] → [..., ...]
                repaired = re.sub(r'\]\s*,\s*\[', ',', raw_steps)
                # Repair 2: stray KV tail after closing ]
                repaired = re.sub(r'\]\s*,\s*"tool".*$', ']', repaired, flags=re.DOTALL)
                # Repair 3: }, ["tool": ... → }, {"tool": ...
                repaired = self._repair_array_open(repaired)
                try:
                    steps_data = json.loads(repaired)
                    if isinstance(steps_data, list) and steps_data:
                        return self._steps_from_json(steps_data)
                except (json.JSONDecodeError, TypeError):
                    pass

        return None

    def _steps_from_json(self, steps_data: list) -> list[Step] | None:
        steps = []
        for item in steps_data:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool", "")
            args = item.get("args", {})
            reason = item.get("reason", "")
            if tool and isinstance(args, dict):
                steps.append(Step(tool=tool, args=args, reason=reason))
        return steps if steps else None

    def _parse_native_steps(self, content: str) -> list[Step] | None:
        """Parse steps from Gemma native KV nesting or bare JSON list format.

        Handles three formats:
          A. steps:[{tool:<|"|>NAME<|"|>, args:{k:<|"|>v<|"|>}, reason:<|"|>R<|"|>}]
             (Gemma native KV nesting — no JSON wrapping)
          B. steps:[{"tool": "NAME", "args": {"k": "v"}, "reason": "R"}]
             (bare JSON list embedded in the tool call body)
        """
        # Find the steps:[...] section — greedy to capture all content
        steps_section = re.search(r'steps:\s*(\[.*\])', content, re.DOTALL)
        if not steps_section:
            return None

        body_raw = steps_section.group(1)

        # Clean up stray <eos> / newlines before attempting JSON
        body_clean = re.sub(r'(<eos>|<\|tool_response\>)', '', body_raw).strip()

        # Path B: strict JSON list
        try:
            steps_data = json.loads(body_clean)
            if isinstance(steps_data, list) and steps_data:
                return self._steps_from_json(steps_data)
        except (json.JSONDecodeError, TypeError):
            pass

        # Path C: JS object literal / mixed format — normalise then parse
        # Handles: {tool: "x", args: {query: "y"}} — unquoted keys
        normalised = self._js_to_json(body_clean)
        if normalised != body_clean:
            try:
                steps_data = json.loads(normalised)
                if isinstance(steps_data, list) and steps_data:
                    return self._steps_from_json(steps_data)
            except (json.JSONDecodeError, TypeError):
                pass

        # Path A: Gemma native KV nesting  (<|"|>…<|"|>)
        steps = []
        for block_m in self._STEP_BLOCK_RE.finditer(body_raw):
            block = block_m.group(0)

            top_kvs = {m.group(1): m.group(2) for m in self._STEP_KV_RE.finditer(block)}
            tool_name = top_kvs.get("tool", "")
            reason = top_kvs.get("reason", "")

            args: dict = {}
            args_m = self._ARGS_BLOCK_RE.search(block)
            if args_m:
                native_args = {m.group(1): m.group(2) for m in self._STEP_KV_RE.finditer(args_m.group(1))}
                if native_args:
                    args = native_args
                else:
                    json_m = self._ARGS_JSON_RE.search(block)
                    if json_m:
                        try:
                            args = json.loads(json_m.group(1))
                        except (json.JSONDecodeError, TypeError):
                            pass
            else:
                json_m = self._ARGS_JSON_RE.search(block)
                if json_m:
                    try:
                        args = json.loads(json_m.group(1))
                    except (json.JSONDecodeError, TypeError):
                        pass

            if tool_name:
                steps.append(Step(tool=tool_name, args=args, reason=reason))

        return steps if steps else None

    # ------------------------------------------------------------------
    # JS-to-JSON normaliser
    # ------------------------------------------------------------------
    # Matches unquoted object keys:  word_chars followed by colon
    _UNQUOTED_KEY_RE = re.compile(r'(?<!["\w])(\b[A-Za-z_]\w*)\s*:', )

    @classmethod
    def _js_to_json(cls, text: str) -> str:
        """Best-effort conversion of JS object literal to JSON.

        Only quotes *unquoted* keys. String values that are already quoted
        are left as-is. Does NOT handle JS comments or single-quoted strings.
        """
        # Quote unquoted keys — skip keys that already sit after a quote
        result = cls._UNQUOTED_KEY_RE.sub(r'"\1":', text)
        return result
