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


def test_bootstrap_does_not_overwrite_existing_config(tmp_path, monkeypatch):
    """config.yaml 已存在时不覆盖（幂等性）"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    # 预先创建 config.yaml（含哨兵内容）
    for sub in ("models", "memory", "logs", "skills"):
        (user_dir / sub).mkdir(parents=True, exist_ok=True)
    sentinel = "# sentinel content\n"
    (user_dir / "config.yaml").write_text(sentinel, encoding="utf-8")

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir()

    assert (user_dir / "config.yaml").read_text(encoding="utf-8") == sentinel


def test_bootstrap_nonexistent_template_falls_back_to_default(tmp_path, monkeypatch):
    """template 路径不存在时写入内置默认配置"""
    import yaml
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=tmp_path / "nonexistent.yaml")

    dest = user_dir / "config.yaml"
    assert dest.exists()
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "model" in data
    assert "agent" in data


def test_bootstrap_copy_failure_falls_back_to_default(tmp_path, monkeypatch):
    """shutil.copy 失败时降级写入内置默认配置"""
    import yaml
    import core.paths as paths_module
    import core.paths
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    def raise_oserror(src, dst):
        raise OSError("copy failed")

    monkeypatch.setattr(core.paths.shutil, "copy", raise_oserror)

    template = tmp_path / "config.yaml"
    template.write_text("model:\n  path: test.gguf\n", encoding="utf-8")

    from core.paths import bootstrap_user_dir
    bootstrap_user_dir(template=template)

    dest = user_dir / "config.yaml"
    assert dest.exists()
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "model" in data
    assert "agent" in data


def test_find_config_prefers_user_dir(tmp_path, monkeypatch):
    """USER_DIR/config.yaml 存在时优先返回"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    user_dir.mkdir(parents=True)
    user_config = user_dir / "config.yaml"
    user_config.write_text("# user config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    # exe_dir 也有 config（确保 user_dir 优先）
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("# exe config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()
    assert result == user_config


def test_find_config_falls_back_to_exe_dir(tmp_path, monkeypatch):
    """USER_DIR 无 config 时 fallback 到 exe_dir"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"  # 不创建 config.yaml
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    (exe_dir / "config.yaml").write_text("# exe config\n", encoding="utf-8")
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()
    assert result == exe_dir / "config.yaml"


def test_find_config_bootstraps_when_neither_exists(tmp_path, monkeypatch):
    """两处均无 config 时触发 bootstrap，返回 USER_DIR/config.yaml"""
    import core.paths as paths_module
    user_dir = tmp_path / "MicroAgent"
    monkeypatch.setattr(paths_module, "USER_DIR", user_dir)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()  # 不放 config.yaml
    monkeypatch.setattr(paths_module, "get_exe_dir", lambda: exe_dir)

    from core.paths import find_config
    result = find_config()

    assert result == user_dir / "config.yaml"
    assert result.exists()
    # 确认子目录也被创建
    assert (user_dir / "models").is_dir()


def test_log_dir_creates_and_returns(tmp_path, monkeypatch):
    """log_dir() 返回 USER_DIR/logs 并确保目录存在"""
    import core.paths as paths_module
    monkeypatch.setattr(paths_module, "USER_DIR", tmp_path / "MicroAgent")
    from core.paths import log_dir
    result = log_dir()
    assert result.is_dir()
    assert result.name == "logs"
