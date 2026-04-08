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
