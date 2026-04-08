# tests/tools/test_file_manager.py
import pytest
from pathlib import Path
from tools.file_manager import (
    ListDirectoryTool,
    ReadFileTool,
    GetFileInfoTool,
    FindFilesTool,
)


def test_list_directory(tmp_path):
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    tool = ListDirectoryTool()
    result = tool.forward(str(tmp_path))
    assert "file.txt" in result
    assert "subdir" in result


def test_list_directory_not_found():
    tool = ListDirectoryTool()
    result = tool.forward("/nonexistent/path")
    assert "不存在" in result


def test_list_directory_not_a_dir(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    tool = ListDirectoryTool()
    result = tool.forward(str(f))
    assert "不是目录" in result


def test_read_file(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world", encoding="utf-8")
    tool = ReadFileTool()
    result = tool.forward(str(f))
    assert result == "hello world"


def test_read_file_not_found():
    tool = ReadFileTool()
    result = tool.forward("/nonexistent/file.txt")
    assert "不存在" in result


def test_get_file_info(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("abc")
    tool = GetFileInfoTool()
    result = tool.forward(str(f))
    assert "test.txt" in result
    assert "字节" in result


def test_find_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("")
    tool = FindFilesTool()
    result = tool.forward(str(tmp_path), "*.py")
    assert "a.py" in result
    assert "c.py" in result
    assert "b.txt" not in result


def test_find_files_no_match(tmp_path):
    tool = FindFilesTool()
    result = tool.forward(str(tmp_path), "*.xyz")
    assert "未找到" in result


from tools.file_manager import (
    WriteFileTool,
    AppendFileTool,
    CreateDirectoryTool,
    MoveFileTool,
    DeleteFileTool,
    create_file_manager_tools,
)
from core.config import FileManagerConfig


# ─── Destructive tools ──────────────────────────────────────────────────────


def test_write_file(tmp_path):
    tool = WriteFileTool(allowed_dirs=[])
    path = str(tmp_path / "out.txt")
    result = tool.forward(path, "hello")
    assert "成功" in result
    assert Path(path).read_text(encoding="utf-8") == "hello"


def test_write_file_respects_allowed_dirs(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool = WriteFileTool(allowed_dirs=[str(allowed)])
    result = tool.forward(str(other / "x.txt"), "data")
    assert "不在允许" in result


def test_append_file(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("line1\n", encoding="utf-8")
    tool = AppendFileTool(allowed_dirs=[])
    tool.forward(str(f), "line2\n")
    assert f.read_text(encoding="utf-8") == "line1\nline2\n"


def test_create_directory(tmp_path):
    tool = CreateDirectoryTool(allowed_dirs=[])
    new_dir = str(tmp_path / "a" / "b" / "c")
    result = tool.forward(new_dir)
    assert "成功" in result
    assert Path(new_dir).is_dir()


def test_move_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("data")
    dst = str(tmp_path / "dst.txt")
    tool = MoveFileTool(allowed_dirs=[])
    result = tool.forward(str(src), dst)
    assert "成功" in result
    assert not src.exists()
    assert Path(dst).read_text() == "data"


def test_delete_file(tmp_path):
    f = tmp_path / "del.txt"
    f.write_text("x")
    tool = DeleteFileTool(allowed_dirs=[])
    result = tool.forward(str(f))
    assert "成功" in result
    assert not f.exists()


def test_delete_file_refuses_directory(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    tool = DeleteFileTool(allowed_dirs=[])
    result = tool.forward(str(d))
    assert "不是文件" in result


def test_create_file_manager_tools_readonly():
    config = FileManagerConfig(allow_destructive=False)
    tools = create_file_manager_tools(config)
    names = [t.name for t in tools]
    assert "list_directory" in names
    assert "read_file" in names
    assert "write_file" not in names
    assert "delete_file" not in names


def test_create_file_manager_tools_destructive():
    config = FileManagerConfig(allow_destructive=True)
    tools = create_file_manager_tools(config)
    names = [t.name for t in tools]
    assert "write_file" in names
    assert "delete_file" in names
