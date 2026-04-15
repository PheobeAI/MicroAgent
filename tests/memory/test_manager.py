# tests/memory/test_manager.py
import logging
import pytest
from memory.manager import MemoryManager
from core.config import MemoryConfig


@pytest.fixture
def manager(tmp_path):
    cfg = MemoryConfig(db_path=str(tmp_path / "manager.db"))
    mgr = MemoryManager(config=cfg, token_counter=lambda msgs: 0)
    yield mgr
    mgr.on_session_end()


def test_manager_instantiates(manager):
    assert manager.store is not None
    assert manager.context is not None  # ContextManager 已在步骤 2 接入


def test_manager_on_session_start_returns_str(manager):
    result = manager.on_session_start()
    assert isinstance(result, str)


def test_manager_on_session_end_does_not_raise(manager):
    manager.on_session_start()
    manager.on_session_end()  # must not raise


def test_manager_facts_crud(manager):
    manager.set_fact("user", "Pheobe")
    assert manager.get_facts()["user"] == "Pheobe"
    manager.delete_fact("user")
    assert "user" not in manager.get_facts()


def test_manager_episode_count(manager):
    assert manager.episode_count() == 0


def test_manager_append_and_get_messages(manager):
    """append_user / append_assistant 正确追加消息并可通过 get_messages_for_llm 取回。"""
    manager.on_session_start()
    manager.append_user("你好")
    manager.append_assistant("你好，有什么可以帮你的？")
    msgs = manager.get_messages_for_llm()
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "你好"}
    assert msgs[1] == {"role": "assistant", "content": "你好，有什么可以帮你的？"}


def test_manager_maybe_compress_returns_bool(manager):
    """maybe_compress 在 token 未超阈值时返回 False，不抛异常。"""
    manager.on_session_start()
    manager.append_user("hi")
    manager.append_assistant("hello")
    result = manager.maybe_compress()
    assert result is False


def test_manager_force_compress_does_not_raise(manager):
    """force_compress 在消息不足时不抛异常。"""
    manager.on_session_start()
    manager.append_user("hi")
    manager.append_assistant("hello")
    manager.force_compress()  # must not raise


def test_manager_token_usage(manager):
    """token_usage 返回合法的 TokenBudget。"""
    from memory.context_manager import TokenBudget
    manager.on_session_start()
    budget = manager.token_usage()
    assert isinstance(budget, TokenBudget)
    assert budget.context_window > 0


def test_manager_prefix_after_session_start(manager):
    """on_session_start 之后 prefix 属性是字符串（可为空）。"""
    manager.on_session_start()
    assert isinstance(manager.prefix, str)


def test_manager_retrieve_episodes_empty(manager):
    """无 episode 时 retrieve_episodes 返回空列表。"""
    manager.on_session_start()
    result = manager.retrieve_episodes("任意查询")
    assert isinstance(result, list)
    assert len(result) == 0


def test_manager_delete_episode(manager, tmp_path):
    """保存后再删除 episode，count 归零。"""
    manager.on_session_start()
    # 手动向 store 存一条 episode
    from memory.store import Episode
    ep_id = manager.store._backend.save_episode(
        Episode(ts="2026-04-14T10:00:00+00:00", summary="test ep")
    )
    assert manager.episode_count() == 1
    manager.delete_episode(ep_id)
    assert manager.episode_count() == 0
