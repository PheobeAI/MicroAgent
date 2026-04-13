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

    def generate(self, messages: list[dict]) -> str:
        """Call the model. Returns raw text content (no parsing)."""
        if self._llm is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=self._config.max_tokens,
        )
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

    # ------------------------------------------------------------------
    # Backward-compat shim — used by tests only, will be removed in Task 9
    # ------------------------------------------------------------------
    def to_smolagents_model(self, show_thinking: bool = True) -> "_LlamaCppSmolagentsModel":
        """Deprecated: wraps the backend in a smolagents-compatible model."""
        return _LlamaCppSmolagentsModel(
            llm=self._llm,
            max_new_tokens=self._config.max_tokens,
            show_thinking=show_thinking,
        )


# ---------------------------------------------------------------------------
# Legacy smolagents wrapper — DEPRECATED, will be removed in Task 9
# ---------------------------------------------------------------------------

try:
    from smolagents.models import (
        Model,
        ChatMessage,
        ChatMessageToolCall,
        ChatMessageToolCallFunction,
        MessageRole,
    )
except ImportError:
    Model = object  # type: ignore
    ChatMessage = None  # type: ignore
    ChatMessageToolCall = None  # type: ignore
    ChatMessageToolCallFunction = None  # type: ignore
    MessageRole = None  # type: ignore


def _parse_gemma_tool_calls(content: str) -> Optional[List]:
    """Parse Gemma native tool-call format into ChatMessageToolCall list.

    Returns None if content contains no Gemma tool calls.
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
            ChatMessageToolCall(
                id=f"call_{i}",
                type="function",
                function=ChatMessageToolCallFunction(name=name, arguments=arguments),
            )
        )
    return tool_calls


class _LlamaCppSmolagentsModel(Model):
    """Deprecated smolagents-compatible wrapper. Use LlamaCppBackend.generate() instead."""

    def __init__(self, llm: Any, max_new_tokens: int = 512, show_thinking: bool = True) -> None:
        super().__init__(flatten_messages_as_text=False, model_id="llama-cpp-local")
        self._llm = llm
        self._max_new_tokens = max_new_tokens
        self._show_thinking = show_thinking

    def generate(self, messages, stop_sequences=None, response_format=None,
                 tools_to_call_from=None, **kwargs) -> "ChatMessage":
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=None,
            response_format=response_format,
            tools_to_call_from=None,
        )
        completion_kwargs["max_tokens"] = self._max_new_tokens
        response = self._llm.create_chat_completion(**completion_kwargs)
        msg = response["choices"][0]["message"]
        content = msg.get("content") or ""
        _log.info("LLM raw output: %r", content[:600] if content else "<empty>")

        # Strip thought blocks before processing
        thought_complete = re.compile(r'<\|channel\>thought(.*?)<channel\|>', re.DOTALL)
        thought_open = re.compile(r'<\|channel\>thought.*', re.DOTALL)
        thoughts = list(thought_complete.finditer(content))
        if thoughts:
            if self._show_thinking:
                import sys
                for t in thoughts:
                    sys.stdout.write(f"\033[2m💭 {t.group(1).strip()}\033[0m\n")
                sys.stdout.flush()
            content = thought_complete.sub("", content).strip()
        else:
            open_m = thought_open.search(content)
            if open_m:
                if self._show_thinking:
                    import sys
                    sys.stdout.write(f"\033[2m💭 {open_m.group(0)[len('<|channel>thought'):].strip()}\033[0m\n")
                    sys.stdout.flush()
                content = thought_open.sub("", content).strip()

        tool_calls = _parse_gemma_tool_calls(content)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content=content if not tool_calls else None,
            tool_calls=tool_calls,
        )