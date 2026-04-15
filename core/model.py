# core/model.py
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from core.config import ModelConfig

_log = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore

# ---------------------------------------------------------------------------
# Gemma native format regexes (kept for backward-compat + _parse_gemma_tool_calls)
# ---------------------------------------------------------------------------
_GEMMA_TOOL_CALL_RE = re.compile(
    r'<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>', re.DOTALL
)
_GEMMA_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)


# ---------------------------------------------------------------------------
# New clean interface
# ---------------------------------------------------------------------------

class ModelBackend(ABC):
    """Abstract inference backend."""

    @abstractmethod
    def load(self) -> None:
        """Load model into memory."""

    @abstractmethod
    def generate(self, messages: list[dict]) -> str:
        """Call the model with a list of chat messages, return raw text output."""

    @abstractmethod
    def get_memory_usage_gb(self) -> float:
        """Return current process RSS in GB."""

    @abstractmethod
    def get_gpu_info(self) -> str:
        """Return short GPU/CPU backend label."""


class LlamaCppBackend(ModelBackend):
    def __init__(self, config: ModelConfig) -> None:
        self._config = config
        self._llm = None

    def load(self) -> None:
        self._llm = Llama(
            model_path=self._config.path,
            n_gpu_layers=self._config.n_gpu_layers,
            n_threads=self._config.n_threads,
            n_ctx=self._config.n_ctx,
            flash_attn=True,
            verbose=False,
        )

    def generate(self, messages: list[dict], json_mode: bool = False) -> str:
        """Call the model. Returns raw text content (no parsing).

        Args:
            messages: Chat messages list.
            json_mode: If True, pass response_format={"type": "json_object"} to
                       constrain output to valid JSON via llama.cpp grammar sampling.
        """
        if self._llm is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        kwargs: dict = {"messages": messages, "max_tokens": self._config.max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._llm.create_chat_completion(**kwargs)
        content = response["choices"][0]["message"].get("content") or ""
        _log.info("LLM raw output: %r", content[:600] if content else "<empty>")
        return content

    def get_memory_usage_gb(self) -> float:
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)

    def get_gpu_info(self) -> str:
        if self._llm is None:
            return "未加载"
        try:
            from llama_cpp import llama_cpp as _lib
            try:
                full_info = _lib.llama_print_system_info().decode("utf-8", errors="replace")
            except Exception:
                full_info = ""
            if full_info:
                _log.info("llama.cpp system info: %s", full_info.strip())
            if not _lib.llama_supports_gpu_offload():
                return "CPU（llama-cpp-python 未编译 GPU 支持）"
            if self._config.n_gpu_layers == 0:
                return "CPU（n_gpu_layers=0）"
            info_upper = full_info.upper()
            if "CUDA" in info_upper:
                backend = "CUDA"
            elif "VULKAN" in info_upper:
                backend = "Vulkan"
            elif "METAL" in info_upper:
                backend = "Metal"
            elif "ROCM" in info_upper:
                backend = "ROCm"
            else:
                backend = "GPU"
            layers = "全部层" if self._config.n_gpu_layers == -1 else f"{self._config.n_gpu_layers} 层"
            return f"{backend}（{layers}）"
        except Exception:
            layers = self._config.n_gpu_layers
            return f"GPU（n_gpu_layers={layers}，无法确认设备）"

# ---------------------------------------------------------------------------
# Stub for backward-compat in existing tests — no smolagents dependency
# ---------------------------------------------------------------------------

class _ToolCallFunction:
    def __init__(self, name: str, arguments: dict) -> None:
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id: str, type: str, function: _ToolCallFunction) -> None:
        self.id = id
        self.type = type
        self.function = function


# Keep old name aliases so test_model.py imports still work
ChatMessageToolCallFunction = _ToolCallFunction
ChatMessageToolCall = _ToolCall


def _parse_gemma_tool_calls(content: str) -> Optional[List]:
    """Parse Gemma native tool-call format.

    Returns list of _ToolCall or None if no Gemma tool calls found.
    """
    matches = list(_GEMMA_TOOL_CALL_RE.finditer(content))
    if not matches:
        return None

    tool_calls = []
    for i, m in enumerate(matches):
        name = m.group(1)
        args_raw = m.group(2)
        arguments = {kv.group(1): kv.group(2) for kv in _GEMMA_KV_RE.finditer(args_raw)}
        tool_calls.append(
            _ToolCall(
                id=f"call_{i}",
                type="function",
                function=_ToolCallFunction(name=name, arguments=arguments),
            )
        )
    return tool_calls
