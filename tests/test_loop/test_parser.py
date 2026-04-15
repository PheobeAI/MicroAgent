# tests/test_loop/test_parser.py
from core.loop.parser import parse_gemma_tool_call, strip_thought_blocks


def test_parse_native_simple():
    content = '<|tool_call>call:web_search{query:<|"|>中东局势<|"|>}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "web_search"
    assert result["args"] == {"query": "中东局势"}


def test_parse_native_multiple_args():
    content = '<|tool_call>call:read_file{path:<|"|>/tmp/a.txt<|"|>, encoding:<|"|>utf-8<|"|>}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "read_file"
    assert result["args"]["path"] == "/tmp/a.txt"
    assert result["args"]["encoding"] == "utf-8"


def test_parse_no_match():
    result = parse_gemma_tool_call("这是普通文字，没有工具调用")
    assert result is None


def test_parse_strips_eos_tokens():
    """模型输出末尾可能带多个 <eos> token，应当被 strip。"""
    content = '<|tool_call>call:web_search{query:<|"|>中东局势<|"|>}<tool_call|><eos><eos><eos>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "web_search"
    assert result["args"] == {"query": "中东局势"}


def test_parse_plan_with_json_value():
    steps_json = '[{"tool": "web_search", "args": {"query": "test"}, "reason": "搜索"}]'
    content = f'<|tool_call>call:plan{{steps:<|"|>{steps_json}<|"|>}}<tool_call|>'
    result = parse_gemma_tool_call(content)
    assert result is not None
    assert result["name"] == "plan"
    assert result["args"]["steps"] == steps_json


def test_strip_complete_thought():
    content = "<|channel>thought\n我需要搜索一下\n<channel|>\n实际输出内容"
    text, thoughts = strip_thought_blocks(content)
    assert "我需要搜索一下" in thoughts[0]
    assert text == "实际输出内容"


def test_strip_truncated_thought():
    content = "<|channel>thought\n思考中，但被截断了"
    text, thoughts = strip_thought_blocks(content)
    assert text == ""
    assert len(thoughts) == 1


def test_parse_paren_format():
    """Bug fix: model sometimes outputs call:NAME(key:<|"|>val<|"|>) with parens instead of braces."""
    raw = '<|tool_call>call:web_search(query:<|"|>Rust 所有权机制是什么<|"|>)\n<eos>'
    result = parse_gemma_tool_call(raw)
    assert result is not None, "Should parse paren-format tool call"
    assert result["name"] == "web_search"
    assert result["args"]["query"] == "Rust 所有权机制是什么"


def test_parse_paren_format_multi_arg():
    """Paren format with multiple args."""
    raw = '<|tool_call>call:memory_store(key:<|"|>user_name<|"|>, value:<|"|>王磊<|"|>)'
    result = parse_gemma_tool_call(raw)
    assert result is not None
    assert result["name"] == "memory_store"
    assert result["args"]["key"] == "user_name"
    assert result["args"]["value"] == "王磊"


def test_strip_no_thought():
    content = "普通内容，没有 thought 块"
    text, thoughts = strip_thought_blocks(content)
    assert text == content
    assert thoughts == []
