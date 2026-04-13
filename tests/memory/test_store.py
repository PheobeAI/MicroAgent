# tests/memory/test_store.py
import pytest
from memory.store import Episode, StorageBackend, SQLiteBackend, MemoryStore


# ── Episode ───────────────────────────────────────────────────────────────────

def test_episode_required_fields():
    ep = Episode(
        ts="2026-04-13T10:00:00+00:00",
        summary="测试摘要",
        topics=[{"name": "CUDA构建", "weight": 0.9}],
        turns=5,
        had_compact=False,
        memory_type="milestone",
        importance=0.8,
    )
    assert ep.ts == "2026-04-13T10:00:00+00:00"
    assert ep.summary == "测试摘要"
    assert ep.topics == [{"name": "CUDA构建", "weight": 0.9}]
    assert ep.turns == 5
    assert ep.had_compact is False
    assert ep.memory_type == "milestone"
    assert ep.importance == 0.8


def test_episode_defaults():
    ep = Episode(ts="2026-04-13T10:00:00+00:00", summary="摘要")
    assert ep.id is None
    assert ep.topics == []
    assert ep.turns == 0
    assert ep.had_compact is False
    assert ep.memory_type == "general"
    assert ep.importance == 0.5


# ── StorageBackend ABC ────────────────────────────────────────────────────────

def test_storage_backend_cannot_instantiate():
    with pytest.raises(TypeError):
        StorageBackend()  # type: ignore


def test_storage_backend_incomplete_subclass_cannot_instantiate():
    class Incomplete(StorageBackend):
        pass

    with pytest.raises(TypeError):
        Incomplete()


# ── SQLiteBackend ─────────────────────────────────────────────────────────────

@pytest.fixture
def backend(tmp_path):
    db = SQLiteBackend(str(tmp_path / "test.db"))
    yield db
    db.close()


def test_sqlite_wal_mode(backend):
    row = backend._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_sqlite_save_and_list_episode(backend):
    ep = Episode(
        ts="2026-04-13T10:00:00+00:00",
        summary="CUDA 构建成功",
        topics=[{"name": "CUDA构建", "weight": 0.9}, {"name": "CI", "weight": 0.4}],
        turns=10,
        had_compact=False,
        memory_type="milestone",
        importance=0.8,
    )
    returned_id = backend.save_episode(ep)
    assert isinstance(returned_id, int) and returned_id > 0

    episodes = backend.list_episodes(limit=10)
    assert len(episodes) == 1
    saved = episodes[0]
    assert saved.id == returned_id
    assert saved.summary == "CUDA 构建成功"
    assert saved.topics == [{"name": "CUDA构建", "weight": 0.9}, {"name": "CI", "weight": 0.4}]
    assert saved.turns == 10
    assert saved.had_compact is False
    assert saved.memory_type == "milestone"
    assert abs(saved.importance - 0.8) < 1e-6


def test_sqlite_list_episodes_order(backend):
    backend.save_episode(Episode(ts="2026-04-11T10:00:00+00:00", summary="旧的"))
    backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00", summary="新的"))
    episodes = backend.list_episodes(limit=10)
    assert episodes[0].summary == "新的"
    assert episodes[1].summary == "旧的"


def test_sqlite_list_episodes_limit(backend):
    for i in range(5):
        backend.save_episode(Episode(ts=f"2026-04-{i+1:02d}T10:00:00+00:00", summary=f"ep{i}"))
    assert len(backend.list_episodes(limit=3)) == 3


def test_sqlite_count_and_delete_episode(backend):
    assert backend.count_episodes() == 0
    ep_id = backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00", summary="待删除"))
    assert backend.count_episodes() == 1
    backend.delete_episode(ep_id)
    assert backend.count_episodes() == 0


def test_sqlite_delete_nonexistent_episode_silent(backend):
    backend.delete_episode(9999)  # should not raise


def test_sqlite_save_fact_upsert(backend):
    backend.save_fact("lang", "zh")
    backend.save_fact("lang", "en")
    facts = backend.get_all_facts()
    assert facts["lang"] == "en"
    assert len(facts) == 1


def test_sqlite_delete_fact(backend):
    backend.save_fact("k", "v")
    backend.delete_fact("k")
    assert backend.get_all_facts() == {}


def test_sqlite_delete_nonexistent_fact_silent(backend):
    backend.delete_fact("nonexistent")  # should not raise


def test_sqlite_close_idempotent(backend):
    backend.close()
    backend.close()  # second call should not raise


def test_sqlite_search_episodes_returns_results(backend):
    backend.save_episode(Episode(ts="2026-04-13T10:00:00+00:00", summary="结果A"))
    backend.save_episode(Episode(ts="2026-04-13T11:00:00+00:00", summary="结果B"))
    results = backend.search_episodes(query="任意查询", top_k=1)
    assert len(results) == 1  # top_k 生效


def test_sqlite_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "test.db"
    db = SQLiteBackend(str(nested))
    db.close()
    assert nested.exists()


# ── MemoryStore ───────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = MemoryStore(SQLiteBackend(str(tmp_path / "store.db")))
    s.load()
    yield s
    s.close()


def test_store_save_and_retrieve(store):
    store.save_episode(
        summary="项目初始化完成",
        topics=[{"name": "项目架构", "weight": 1.0}, {"name": "初始化", "weight": 1.0}],
        turns=3,
        had_compact=False,
        memory_type="milestone",
        importance=0.8,
    )
    results = store.retrieve_episodes(query="初始化", top_k=5)
    assert len(results) == 1
    assert results[0].summary == "项目初始化完成"
    assert results[0].topics == [{"name": "项目架构", "weight": 1.0},
                                  {"name": "初始化", "weight": 1.0}]


def test_store_get_topic_index_weighted(store):
    store.save_episode(summary="A",
                       topics=[{"name": "CUDA构建", "weight": 0.9},
                               {"name": "CI", "weight": 0.4}],
                       turns=1, had_compact=False, memory_type="general", importance=0.5)
    store.save_episode(summary="B",
                       topics=[{"name": "CUDA构建", "weight": 0.6},
                               {"name": "项目架构", "weight": 1.0}],
                       turns=1, had_compact=False, memory_type="general", importance=0.5)
    store.save_episode(summary="C",
                       topics=[{"name": "项目架构", "weight": 0.8}],
                       turns=1, had_compact=False, memory_type="general", importance=0.5)

    index = store.get_topic_index(limit=10)
    assert abs(index["项目架构"] - 1.8) < 1e-6
    assert abs(index["CUDA构建"] - 1.5) < 1e-6
    assert abs(index["CI"] - 0.4) < 1e-6
    keys = list(index.keys())
    assert keys[0] == "项目架构"
    assert keys[1] == "CUDA构建"


def test_store_get_topic_index_limit(store):
    for i in range(15):
        store.save_episode(summary=f"ep{i}",
                           topics=[{"name": f"topic{i}", "weight": 1.0}],
                           turns=1, had_compact=False, memory_type="general", importance=0.5)
    assert len(store.get_topic_index(limit=10)) == 10


def test_store_facts_crud(store):
    store.set_fact("lang", "zh")
    assert store.get_all_facts()["lang"] == "zh"
    store.set_fact("lang", "en")
    assert store.get_all_facts()["lang"] == "en"
    store.delete_fact("lang")
    assert "lang" not in store.get_all_facts()


def test_store_count_and_delete_episode(store):
    assert store.count_episodes() == 0
    store.save_episode(summary="x", topics=[], turns=1,
                       had_compact=False, memory_type="general", importance=0.5)
    assert store.count_episodes() == 1
    ep_id = store.retrieve_episodes(query="", top_k=5)[0].id
    store.delete_episode(ep_id)
    assert store.count_episodes() == 0
