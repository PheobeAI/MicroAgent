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
        # Guard against path traversal via pattern
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            return "错误：不支持包含路径遍历的搜索模式"
        matches = sorted(p.rglob(pattern))
        if not matches:
            return f"未找到匹配 '{pattern}' 的文件"
        lines = [str(m.relative_to(p)) for m in matches]
        return f"找到 {len(matches)} 个匹配文件:\n" + "\n".join(lines)


# ─── Destructive tools ────────────────────────────────────────────────────────


class _DestructiveTool(MicroTool):
    """Mixin for tools that check allowed_dirs before operating."""

    def __init__(self, allowed_dirs: List[str]) -> None:
        super().__init__()
        self._allowed = [Path(d).resolve() for d in allowed_dirs] if allowed_dirs else []

    def _check_allowed(self, path: Path) -> bool:
        if not self._allowed:
            return True
        resolved = path.resolve()
        return any(resolved == d or d in resolved.parents for d in self._allowed)

    def _guard(self, path: Path) -> str | None:
        if not self._check_allowed(path):
            return f"错误：路径 {path} 不在允许的目录范围内"
        return None


class WriteFileTool(_DestructiveTool):
    name = "write_file"
    description = "将内容写入文件（会覆盖已有内容）。需要 allow_destructive: true。"
    inputs = {
        "path": {"type": "string", "description": "目标文件路径"},
        "content": {"type": "string", "description": "要写入的文本内容"},
    }
    output_type = "string"

    def forward(self, path: str, content: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"成功写入 {len(content)} 字符到 {path}"
        except Exception as e:
            return f"错误：写入文件失败: {e}"


class AppendFileTool(_DestructiveTool):
    name = "append_file"
    description = "向已有文件末尾追加内容。需要 allow_destructive: true。"
    inputs = {
        "path": {"type": "string", "description": "目标文件路径"},
        "content": {"type": "string", "description": "要追加的文本内容"},
    }
    output_type = "string"

    def forward(self, path: str, content: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(content)
            return f"成功追加 {len(content)} 字符到 {path}"
        except Exception as e:
            return f"错误：追加文件失败: {e}"


class CreateDirectoryTool(_DestructiveTool):
    name = "create_directory"
    description = "创建目录（包含所有中间目录，等效于 mkdir -p）。需要 allow_destructive: true。"
    inputs = {"path": {"type": "string", "description": "要创建的目录路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        p.mkdir(parents=True, exist_ok=True)
        return f"成功创建目录: {path}"


class MoveFileTool(_DestructiveTool):
    name = "move_file"
    description = "移动或重命名文件。需要 allow_destructive: true。"
    inputs = {
        "src": {"type": "string", "description": "源文件路径"},
        "dst": {"type": "string", "description": "目标路径"},
    }
    output_type = "string"

    def forward(self, src: str, dst: str) -> str:
        s, d = Path(src), Path(dst)
        if err := self._guard(s):
            return err
        if err := self._guard(d):
            return err
        if not s.exists():
            return f"错误：源文件不存在: {src}"
        s.rename(d)
        return f"成功移动 {src} -> {dst}"


class DeleteFileTool(_DestructiveTool):
    name = "delete_file"
    description = "删除单个文件（不删除目录）。需要 allow_destructive: true。"
    inputs = {"path": {"type": "string", "description": "要删除的文件路径"}}
    output_type = "string"

    def forward(self, path: str) -> str:
        p = Path(path)
        if err := self._guard(p):
            return err
        if not p.exists():
            return f"错误：文件不存在: {path}"
        if not p.is_file():
            return f"错误：{path} 不是文件（拒绝删除目录）"
        p.unlink()
        return f"成功删除: {path}"


# ─── Factory ─────────────────────────────────────────────────────────────────


def create_file_manager_tools(config: FileManagerConfig) -> List[MicroTool]:
    read_tools: List[MicroTool] = [
        ListDirectoryTool(),
        ReadFileTool(),
        GetFileInfoTool(),
        FindFilesTool(),
    ]
    if not config.allow_destructive:
        return read_tools

    destructive_tools: List[MicroTool] = [
        WriteFileTool(config.allowed_dirs),
        AppendFileTool(config.allowed_dirs),
        CreateDirectoryTool(config.allowed_dirs),
        MoveFileTool(config.allowed_dirs),
        DeleteFileTool(config.allowed_dirs),
    ]
    return read_tools + destructive_tools
