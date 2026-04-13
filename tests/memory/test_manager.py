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
    assert manager.context is None  # 步骤 2 才接入 ContextManager


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


def test_manager_stub_methods_warn_not_raise(manager, caplog):
    with caplog.at_level(logging.WARNING, logger="memory.manager"):
        result = manager.get_messages_for_llm()
        assert result == []

        manager.append_message({"role": "user", "content": "hi"})

        compressed = manager.maybe_compress()
        assert compressed is False

        manager.force_compress()

    warned_methods = [r.message for r in caplog.records]
    assert any("get_messages_for_llm" in m for m in warned_methods)
    assert any("append_message" in m for m in warned_methods)
    assert any("maybe_compress" in m for m in warned_methods)
    assert any("force_compress" in m for m in warned_methods)
