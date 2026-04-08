# tools/file_manager.py
from pathlib import Path
from typing import List

from tools.base import MicroTool
from core.config import FileManagerConfig


# ─── Read-only tools ────────────────────────────────────────────────────────


class ListDirectoryTool(MicroTool):
    name = "list_directory"
    description = "列出指定目录下的文件和子目录。"
    inputs = {"path": {"type": "string", "description": "要列出内容的目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：路径不存在: {path}"
        if not p.is_dir():
            return f"错误：{path} 不是目录"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        if not items:
            return f"{path} (空目录)"
        lines = [f"[DIR]  {i.name}" if i.is_dir() else f"[FILE] {i.name}" for i in items]
        return f"{path} ({len(items)} 项):\n" + "\n".join(lines)


class ReadFileTool(MicroTool):
    name = "read_file"
    description = "读取文本文件的完整内容并返回。"
    inputs = {"path": {"type": "string", "description": "要读取的文件路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：文件不存在: {path}"
        if not p.is_file():
            return f"错误：{path} 不是文件"
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"错误：无法读取文件: {e}"


class GetFileInfoTool(MicroTool):
    name = "get_file_info"
    description = "获取文件或目录的元信息，包括大小、修改时间、类型。"
    inputs = {"path": {"type": "string", "description": "要查询的文件或目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"错误：路径不存在: {path}"
        stat = p.stat()
        import datetime
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        kind = "目录" if p.is_dir() else "文件"
        return (
            f"名称: {p.name}\n"
            f"类型: {kind}\n"
            f"大小: {stat.st_size} 字节\n"
            f"修改时间: {mtime}"
        )


class FindFilesTool(MicroTool):
    name = "find_files"
    description = "在指定目录下递归搜索匹配文件名模式的文件（支持通配符，如 *.py）。"
    inputs = {
        "directory": {"type": "string", "description": "搜索的根目录"},
        "pattern": {"type": "string", "description": "文件名匹配模式，如 *.txt 或 *.py"},
    }
    output_type = "string"

    def forward(self, directory: str, pattern: str) -> str:
        p = Path(directory)
        if not p.exists():
            return f"错误：目录不存在: {directory}"
        matches = sorted(p.rglob(pattern))
        if not matches:
            return f"未找到匹配 '{pattern}' 的文件"
        lines = [str(m.relative_to(p)) for m in matches]
        return f"找到 {len(matches)} 个匹配文件:\n" + "\n".join(lines)


# ─── Factory (placeholder for Task 6) ────────────────────────────────────────


def create_file_manager_tools(config: FileManagerConfig) -> List[MicroTool]:
    return [
        ListDirectoryTool(),
        ReadFileTool(),
        GetFileInfoTool(),
        FindFilesTool(),
    ]
