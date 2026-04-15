# tests/test_tools/test_memory_tools.py
"""Tests for MemoryRecallTool, MemoryStoreTool, MemoryForgetTool."""
import pytest
from unittest.mock import MagicMock
from tools.memory_tools import MemoryRecallTool, MemoryStoreTool, MemoryForgetTool
from memory.store import Episode


def make_memory(episodes=None, facts=None):
    mem = MagicMock()
    mem.retrieve_episodes.return_value = episodes or []
    mem.get_facts.return_value = facts or {}
    return mem


# ── MemoryRecallTool ──────────────────────────────────────────────────────────

def test_recall_empty_query_returns_error():
    tool = MemoryRecallTool(make_memory())
    result = tool()
    assert "错误" in result


def test_recall_no_results_returns_message():
    tool = MemoryRecallTool(make_memory(episodes=[]))
    result = tool(query="不存在的话题")
    assert "未找到" in result


def test_recall_returns_formatted_episodes():
    ep = Episode(
        ts="2026-04-14T10:00:00+00:00",
        summary="CUDA构建成功",
        topics=[{"name": "CUDA构建", "weight": 0.9}],
        memory_type="milestone",
    )
    tool = MemoryRecallTool(make_memory(episodes=[ep]))
    result = tool(query="CUDA")
    assert "CUDA构建" in result
    assert "CUDA构建成功" in result
    assert "2026-04-14" in result


def test_recall_handles_string_topics():
    """topics 里可能是纯字符串（旧格式兼容）。"""
    ep = Episode(
        ts="2026-04-14T10:00:00+00:00",
        summary="测试摘要",
        topics=["topic_string"],
        memory_type="general",
    )
    tool = MemoryRecallTool(make_memory(episodes=[ep]))
    result = tool(query="测试")
    assert "topic_string" in result


# ── MemoryStoreTool ───────────────────────────────────────────────────────────

def test_store_sets_fact():
    mem = make_memory()
    tool = MemoryStoreTool(mem)
    result = tool(key="lang", value="zh")
    mem.set_fact.assert_called_once_with("lang", "zh")
    assert "lang" in result
    assert "zh" in result


def test_store_missing_key_returns_error():
    tool = MemoryStoreTool(make_memory())
    result = tool(value="zh")
    assert "错误" in result


def test_store_missing_value_returns_error():
    tool = MemoryStoreTool(make_memory())
    result = tool(key="lang")
    assert "错误" in result


# ── MemoryForgetTool ──────────────────────────────────────────────────────────

def test_forget_by_key_calls_delete_fact():
    mem = make_memory()
    tool = MemoryForgetTool(mem)
    result = tool(key="lang")
    mem.delete_fact.assert_called_once_with("lang")
    assert "lang" in result


def test_forget_by_episode_id_calls_delete_episode():
    mem = make_memory()
    tool = MemoryForgetTool(mem)
    result = tool(episode_id=42)
    mem.delete_episode.assert_called_once_with(42)
    assert "42" in result


def test_forget_episode_id_as_string_is_cast_to_int():
    mem = make_memory()
    tool = MemoryForgetTool(mem)
    result = tool(episode_id="7")
    mem.delete_episode.assert_called_once_with(7)


def test_forget_invalid_episode_id_returns_error():
    tool = MemoryForgetTool(make_memory())
    result = tool(episode_id="not_a_number")
    assert "错误" in result


def test_forget_no_args_returns_error():
    tool = MemoryForgetTool(make_memory())
    result = tool()
    assert "错误" in result


def test_forget_key_takes_priority_over_episode_id():
    """同时提供 key 和 episode_id 时，key 优先。"""
    mem = make_memory()
    tool = MemoryForgetTool(mem)
    result = tool(key="lang", episode_id=42)
    mem.delete_fact.assert_called_once_with("lang")
    mem.delete_episode.assert_not_called()
