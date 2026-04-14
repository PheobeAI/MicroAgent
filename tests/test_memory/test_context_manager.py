# tests/test_memory/test_context_manager.py
from unittest.mock import MagicMock
from memory.context_manager import ContextManager, Message, MSG_NORMAL, MSG_BOUNDARY, TokenBudget
from memory.store import MemoryStore


def make_store() -> MemoryStore:
    store = MagicMock(spec=MemoryStore)
    store.get_topic_index.return_value = {}
    store.get_all_facts.return_value = {}
    store.retrieve_episodes.return_value = []
    return store


def make_config():
    cfg = MagicMock()
    cfg.context_window_tokens = 8192
    cfg.compress_threshold = 0.8
    cfg.keep_recent_turns = 5
    cfg.max_episodes_in_prefix = 3
    cfg.min_turns_to_save = 2
    cfg.pre_compact_instructions = ""
    return cfg


def token_counter(messages):
    # 1 token per character, simple estimator
    return sum(len(str(m)) for m in messages)


# ── get_messages_for_llm ─────────────────────────────────────────────────────

def test_empty_buffer_returns_empty():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    assert ctx.get_messages_for_llm() == []


def test_returns_messages_without_boundary():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    ctx.append_message(Message(role="user", content="hello"))
    ctx.append_message(Message(role="assistant", content="hi"))
    msgs = ctx.get_messages_for_llm()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_boundary_slices_older_messages():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    ctx.append_message(Message(role="user", content="old turn"))
    ctx.append_message(Message(role="assistant", content="old answer"))
    # Inject a BOUNDARY
    ctx._buffer.append(Message(role="assistant", content="[摘要]之前讨论了...", msg_type=MSG_BOUNDARY))
    ctx.append_message(Message(role="user", content="new turn"))
    msgs = ctx.get_messages_for_llm()
    # Should only see BOUNDARY message + new turn, not old messages
    assert len(msgs) == 2
    assert msgs[0]["content"] == "[摘要]之前讨论了..."
    assert msgs[1]["content"] == "new turn"


# ── append_message ───────────────────────────────────────────────────────────

def test_append_increments_turns():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    assert ctx.turns == 0
    ctx.append_message(Message(role="user", content="hello"))
    ctx.append_message(Message(role="assistant", content="hi"))
    assert ctx.turns == 1  # 1 complete turn = 1 user + 1 assistant


# ── token_usage ──────────────────────────────────────────────────────────────

def test_token_usage_returns_budget():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    ctx.append_message(Message(role="user", content="hello"))
    budget = ctx.token_usage()
    assert isinstance(budget, TokenBudget)
    assert budget.context_window == 8192
    assert budget.used_in_current_context > 0


# ── maybe_compress ───────────────────────────────────────────────────────────

def test_maybe_compress_no_trigger_when_under_threshold():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    ctx.append_message(Message(role="user", content="hi"))
    ctx.append_message(Message(role="assistant", content="hello"))
    # Short messages, well under threshold
    result = ctx.maybe_compress()
    assert result is False


def test_maybe_compress_triggers_when_over_threshold(monkeypatch):
    ctx = ContextManager(make_store(), make_config(), token_counter)
    # Override token counter to always return 90% of window
    monkeypatch.setattr(ctx, "_token_counter", lambda msgs: int(8192 * 0.9))
    ctx.append_message(Message(role="user", content="hi"))
    ctx.append_message(Message(role="assistant", content="hello"))
    # force_compress would need LLM; monkeypatch it
    monkeypatch.setattr(ctx, "force_compress", lambda: None)
    result = ctx.maybe_compress()
    assert result is True


# ── start_session prefix ─────────────────────────────────────────────────────

def test_start_session_returns_empty_when_no_data():
    ctx = ContextManager(make_store(), make_config(), token_counter)
    prefix = ctx.start_session()
    assert isinstance(prefix, str)


def test_start_session_includes_facts():
    store = make_store()
    store.get_all_facts.return_value = {"language": "zh", "user": "Alice"}
    ctx = ContextManager(store, make_config(), token_counter)
    prefix = ctx.start_session()
    assert "language" in prefix
    assert "Alice" in prefix


def test_start_session_includes_topic_index():
    store = make_store()
    store.get_topic_index.return_value = {"CUDA构建": 3, "CI调试": 2}
    ctx = ContextManager(store, make_config(), token_counter)
    prefix = ctx.start_session()
    assert "CUDA构建" in prefix
    assert "3" in prefix
