# core/model.py
import re
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from core.config import ModelConfig

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore

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

# Gemma tool-call format:
# <|tool_call>call:TOOL_NAME{key:<|"|>value<|"|>, ...}<tool_call|>
_GEMMA_TOOL_CALL_RE = re.compile(
    r'<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>', re.DOTALL
)
_GEMMA_KV_RE = re.compile(r'(\w+):<\|"\|>(.*?)<\|"\|>', re.DOTALL)


def _parse_gemma_tool_calls(content: str) -> Optional[List]:
    """Detect and parse Gemma native tool-call format into ChatMessageToolCall list.

    Returns None if the content contains no Gemma tool calls, so the caller
    can fall back to letting smolagents parse JSON from the content instead.
    """
    matches = list(_GEMMA_TOOL_CALL_RE.finditer(content))
    if not matches:
        return None

    tool_calls = []
    for i, m in enumerate(matches):
        name = m.group(1)
        args_raw = m.group(2)

        # Parse key:<|"|>value<|"|> pairs (handles colons/special chars in values)
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
    """smolagents-compatible Model wrapper around a llama-cpp-python Llama instance."""

    def __init__(self, llm: Any, max_new_tokens: int = 512) -> None:
        super().__init__(flatten_messages_as_text=False, model_id="llama-cpp-local")
        self._llm = llm
        self._max_new_tokens = max_new_tokens

    def generate(
        self,
        messages,
        stop_sequences=None,
        response_format=None,
        tools_to_call_from=None,
        **kwargs,
    ) -> "ChatMessage":
        # Do NOT pass tools_to_call_from to llama-cpp. When passed, llama-cpp
        # enables Gemma's native chat template which outputs tool calls as
        # special tokens that are stripped from the `content` field, leaving
        # content='' — our regex parser then finds nothing and smolagents
        # raises a JSON parse error.
        #
        # Tool descriptions are already injected by smolagents into the system
        # prompt as text. The model outputs tool calls as inline text
        # (<|tool_call>call:NAME{...}<tool_call|>), which _parse_gemma_tool_calls
        # can match reliably.
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=stop_sequences,
            response_format=response_format,
            tools_to_call_from=None,
        )
        completion_kwargs["max_tokens"] = self._max_new_tokens

        response = self._llm.create_chat_completion(**completion_kwargs)

        msg = response["choices"][0]["message"]
        content = msg.get("content") or ""

        # llama-cpp fails to parse Gemma's native tool format into tool_calls,
        # so we parse it ourselves from the raw content.
        tool_calls = _parse_gemma_tool_calls(content)

        return ChatMessage(
            role=MessageRole(msg["role"]),
            content=None if tool_calls else content,
            tool_calls=tool_calls,
            raw=response,
        )


class ModelBackend(ABC):
    """Abstract backend — swap implementations to change inference engine."""

    @abstractmethod
    def load(self) -> None:
        """Load model into memory. Call once before to_smolagents_model()."""

    @abstractmethod
    def get_memory_usage_gb(self) -> float:
        """Return current process RSS in GB."""

    @abstractmethod
    def to_smolagents_model(self) -> Any:
        """Return a smolagents-compatible model object."""


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
            verbose=False,
        )

    def get_memory_usage_gb(self) -> float:
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)

    def to_smolagents_model(self) -> Any:
        if self._llm is None:
            raise RuntimeError("Model has not been loaded. Call load() first.")
        return _LlamaCppSmolagentsModel(self._llm, max_new_tokens=self._config.max_tokens)
