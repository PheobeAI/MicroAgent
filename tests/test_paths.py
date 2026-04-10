# tests/test_paths.py
from pathlib import Path


def test_resolve_relative_absolute_passthrough(tmp_path):
    """绝对路径直通，不做任何修改"""
    from core.paths import resolve_relative
    abs_path = str(tmp_path / "model.gguf")
    result = resolve_relative(tmp_path, abs_path)
    assert result == Path(abs_path)


def test_resolve_relative_resolves_against_config_dir(tmp_path):
    """相对路径相对于 config_dir 解析"""
    from core.paths import resolve_relative
    result = resolve_relative(tmp_path, r"models\foo.gguf")
    assert result == (tmp_path / "models" / "foo.gguf").resolve()
