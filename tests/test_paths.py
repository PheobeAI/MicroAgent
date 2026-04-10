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


def test_bootstrap_creates_subdirs(tmp_path, monkeypatch):
    """bootstrap_user_dir 创建四个子目录"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    from core.paths import bootstrap_user_dir
    result = bootstrap_user_dir()

    assert result == user_dir
    for sub in ("models", "memory", "logs", "skills"):
        assert (user_dir / sub).is_dir(), f"缺少子目录: {sub}"


def test_bootstrap_copies_template(tmp_path, monkeypatch):
    """提供 template 时复制其内容"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    template = tmp_path / "config.yaml"
    template.write_text("model:\n  path: test.gguf\n", encoding="utf-8")

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=template)

    dest = user_dir / "config.yaml"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "model:\n  path: test.gguf\n"


def test_bootstrap_writes_default_when_no_template(tmp_path, monkeypatch):
    """无 template 时写入内置默认配置，文件可被 yaml.safe_load 解析"""
    import yaml
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=None)

    dest = user_dir / "config.yaml"
    assert dest.exists()
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "model" in data
    assert "agent" in data
