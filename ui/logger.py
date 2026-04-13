# ui/logger.py
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from core.paths import log_dir

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHF]')


class _FileStream:
    """File-only stream — never writes to the terminal."""

    def __init__(self, path: Path) -> None:
        self._f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, text: str) -> int:
        return self._f.write(_ANSI_RE.sub('', text))

    def flush(self) -> None:
        self._f.flush()

    def fileno(self) -> int:
        return self._f.fileno()

    @property
    def encoding(self) -> str:
        return "utf-8"

    def isatty(self) -> bool:
        return False


def setup(log_level: str = "debug") -> Path:
    """Set up file-based logging.

    ``log_level`` controls only what is written to the log *file* — it has no
    effect on what the console displays.  The console verbosity is governed
    separately by ``runtime.console_verbose`` / ``agent.verbose`` in config.

    Must be called AFTER ui.console is imported (so our Rich Console already
    captured the real stdout) but BEFORE the smolagents agent is created (so
    smolagents' internal Rich Console picks up the redirected stdout and writes
    to the log file instead of the terminal).

    Returns the log file path.
    """
    log_file = log_dir() / f"microagent_{datetime.now():%Y-%m-%d}.log"

    # Resolve the requested file log level; fall back to DEBUG so we never
    # silently discard diagnostic information.
    file_level = getattr(logging, log_level.upper(), logging.DEBUG)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(file_level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger()
    # Root logger must be at least as permissive as the file handler so that
    # records aren't dropped before they reach the handler.
    root.setLevel(file_level)
    root.addHandler(handler)

    stream = _FileStream(log_file)
    sys.stdout = stream  # type: ignore[assignment]
    sys.stderr = stream  # type: ignore[assignment]

    # Also redirect the OS-level file descriptor 2 (C-library stderr) to the
    # log file, so llama.cpp diagnostic messages don't appear in the terminal.
    _fd = os.open(str(log_file), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
    os.dup2(_fd, 2)
    os.close(_fd)

    return log_file
