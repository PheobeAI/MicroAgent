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

# Gemma thinking/reasoning channel blocks:
# <|channel>thought ... <channel|>
# Also handles truncated blocks where <channel|> closing tag is missing.
_GEMMA_THOUGHT_RE = re.compile(
    r'<\|channel\>thought(.*?)<channel\|>', re.DOTALL
)
# Truncated thought block: opened but never closed (model was cut off by max_tokens)
_GEMMA_THOUGHT_OPEN_RE = re.compile(
    r'<\|channel\>thought.*', re.DOTALL
)

# JSON object pattern (handles one level of nesting)
_JSON_OBJ_RE = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)

# Gemma hybrid format: <|tool_call>call:TOOLNAME{...json body...}
# The model sometimes uses the Gemma prefix but with a JSON body instead of
# the native <|"|>key<|"|> KV pairs, and omits the <tool_call|> closing tag.
_GEMMA_HYBRID_RE = re.compile(
    r'<\|tool_call\>call:(\w+)(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', re.DOTALL
)


def _parse_json_tool_calls(content: str) -> Optional[List]:
    """Parse smolagents JSON-format tool calls from content.

    smolagents ToolCallingAgent asks the model to respond with:
        Action:
        {"name": "tool_name", "arguments": "value_or_dict"}

    The model may output one or more such JSON blobs.  We scan for all
    top-level JSON objects that have a "name" key and convert them to
    ChatMessageToolCall objects.

    Note: when "arguments" is a bare string (not a dict), we treat it as
    the value of the "answer" key for final_answer, or wrap it in {"input":
    ...} for other tools — matching what the callers expect.
    """
    import json as _json

    tool_calls = []
    for m in _JSON_OBJ_RE.finditer(content):
        try:
            data = _json.loads(m.group())
        except _json.JSONDecodeError:
            continue

        name = data.get("name")
        if not name or not isinstance(name, str):
            continue

        args = data.get("arguments", {})
        if isinstance(args, str):
            # Bare string argument — wrap appropriately per tool convention.
            args = {"answer": args} if name == "final_answer" else {"input": args}
        elif not isinstance(args, dict):
            args = {"input": str(args)}

        tool_calls.append(
            ChatMessageToolCall(
                id=f"call_{len(tool_calls)}",
                type="function",
                function=ChatMessageToolCallFunction(name=name, arguments=args),
            )
        )

    return tool_calls if tool_calls else None


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

    def __init__(self, llm: Any, max_new_tokens: int = 512, show_thinking: bool = True) -> None:
        super().__init__(flatten_messages_as_text=False, model_id="llama-cpp-local")
        self._llm = llm
        self._max_new_tokens = max_new_tokens
        self._show_thinking = show_thinking

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

        # Log raw model output at INFO level so we can diagnose format issues.
        import logging as _logging
        _log = _logging.getLogger(__name__)
        _log.info("LLM raw output: %r", content[:800] if content else "<empty>")

        # Strip Gemma thought/reasoning channel blocks before parsing.
        # <|channel>thought ... <channel|> is the model's internal reasoning and
        # must not be surfaced to the user or treated as a tool call / final answer.
        #
        # Two cases:
        #   1. Complete block: <|channel>thought ... <channel|>  → strip via regex
        #   2. Truncated block: <|channel>thought ... (no closing tag, model was
        #      cut off by max_tokens)  → strip everything from <|channel>thought onward
        thought_matches = list(_GEMMA_THOUGHT_RE.finditer(content))
        if thought_matches:
            # Case 1: complete thought block(s)
            for tm in thought_matches:
                thought_text = tm.group(1).strip()
                _log.debug("LLM thought block (stripped): %s", thought_text[:400])
                if self._show_thinking and thought_text:
                    import sys as _sys
                    out = getattr(_sys, "__stdout__", None)
                    if out is not None:
                        out.write(f"\033[2m💭 {thought_text}\033[0m\n")
                        out.flush()
            content_for_parse = _GEMMA_THOUGHT_RE.sub("", content).strip()
            _log.info("LLM content after stripping thought blocks: %r", content_for_parse[:400])
        elif _GEMMA_THOUGHT_OPEN_RE.search(content):
            # Case 2: truncated thought block — model was cut off inside thought
            _log.warning(
                "LLM thought block was truncated (max_tokens too small). "
                "Consider increasing max_tokens in config. Stripping partial thought."
            )
            # Extract and optionally display the partial thought text
            open_match = _GEMMA_THOUGHT_OPEN_RE.search(content)
            if open_match and self._show_thinking:
                partial = open_match.group(0).replace("<|channel>thought", "").strip()
                if partial:
                    import sys as _sys
                    out = getattr(_sys, "__stdout__", None)
                    if out is not None:
                        out.write(f"\033[2m💭 [思考被截断] {partial}\033[0m\n")
                        out.flush()
            content_for_parse = _GEMMA_THOUGHT_OPEN_RE.sub("", content).strip()
            _log.info("LLM content after stripping truncated thought: %r", content_for_parse[:400])
        else:
            content_for_parse = content

        # Strategy 1: Gemma native format  <|tool_call>call:NAME{key:<|"|>val<|"|>}<tool_call|>
        tool_calls = _parse_gemma_tool_calls(content_for_parse)

        # Strategy 1.5: Gemma hybrid format  <|tool_call>call:NAME{...json body...}
        # The model uses the Gemma prefix but JSON body without <tool_call|> closing tag.
        # e.g.  <|tool_call>call:final_answer{"answer": "..."}
        if tool_calls is None:
            import json as _json
            hybrid_matches = list(_GEMMA_HYBRID_RE.finditer(content_for_parse))
            if hybrid_matches:
                hybrid_calls = []
                for i, hm in enumerate(hybrid_matches):
                    name = hm.group(1)
                    raw_body = hm.group(2)
                    args = None
                    # First try strict JSON parse
                    try:
                        args = _json.loads(raw_body)
                    except _json.JSONDecodeError:
                        # Fallback: model may output JS-style unquoted keys
                        # e.g. {answer: "..."} → {"answer": "..."}
                        fixed = re.sub(r'(\{|,)\s*(\w+)\s*:', r'\1 "\2":', raw_body)
                        try:
                            args = _json.loads(fixed)
                        except _json.JSONDecodeError:
                            _log.warning("Strategy 1.5: failed to parse body %r", raw_body[:100])
                    if args is None:
                        continue
                    if not isinstance(args, dict):
                        args = {"input": str(args)}
                    hybrid_calls.append(
                        ChatMessageToolCall(
                            id=f"call_{i}",
                            type="function",
                            function=ChatMessageToolCallFunction(name=name, arguments=args),
                        )
                    )
                if hybrid_calls:
                    _log.info("Parsed %d tool call(s) via Gemma hybrid format", len(hybrid_calls))
                    tool_calls = hybrid_calls

        # Strategy 2: smolagents JSON format  {"name": "...", "arguments": ...}
        # (the model follows smolagents' system prompt instructions and outputs JSON)
        if tool_calls is None:
            tool_calls = _parse_json_tool_calls(content_for_parse)

        # NOTE: No plain-text fallback (Strategy 3 removed).
        # If neither Gemma-native nor JSON tool calls are found, we return the
        # content as-is and let smolagents handle the error / retry naturally.
        # Silently synthesizing final_answer masks format bugs and makes debugging
        # harder — if the model isn't following the tool-call protocol, we want
        # to see that failure explicitly in logs, not hide it.
        if tool_calls is None and content_for_parse.strip():
            _log.warning(
                "LLM output contained no tool call (neither Gemma-native nor JSON). "
                "Raw content: %r", content_for_parse[:300]
            )

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
            # Flash Attention is required for Gemma's SWA (Sliding Window Attention)
            # architecture when n_ctx < n_ctx_train. Without it, llama.cpp pads the
            # V cache to 512 tokens, causing the model to output <eos> when prompt
            # exceeds that limit (empty content, completion_tokens=3).
            flash_attn=True,
            verbose=False,
        )

    def get_memory_usage_gb(self) -> float:
        import psutil
        return psutil.Process().memory_info().rss / (1024 ** 3)

    def get_gpu_info(self) -> str:
        """Return a short GPU/CPU backend label for the startup banner.

        Only "CUDA", "Vulkan", "CPU" (etc.) are shown on the console.
        The full llama_print_system_info() output is written to the log file
        at DEBUG level so detailed hardware info is always available there.
        """
        import logging
        log = logging.getLogger(__name__)

        if self._llm is None:
            return "未加载"

        try:
            from llama_cpp import llama_cpp as _lib

            # Dump full system info to the log file (DEBUG level).
            try:
                info_bytes = _lib.llama_print_system_info()
                full_info = info_bytes.decode("utf-8", errors="replace") if info_bytes else ""
            except Exception:
                full_info = ""
            if full_info:
                log.info("llama.cpp system info: %s", full_info.strip())

            # No GPU support compiled in → pure CPU.
            if not _lib.llama_supports_gpu_offload():
                return "CPU（llama-cpp-python 未编译 GPU 支持）"

            # n_gpu_layers=0 means user explicitly chose CPU.
            cfg_layers = self._config.n_gpu_layers
            if cfg_layers == 0:
                return "CPU（n_gpu_layers=0）"

            # Detect backend from system info keywords.
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

            layers_label = "全部层" if cfg_layers == -1 else f"{cfg_layers} 层"
            return f"{backend}（{layers_label}）"

        except Exception:
            cfg_layers = self._config.n_gpu_layers
            if cfg_layers == 0:
                return "CPU（n_gpu_layers=0）"
            return f"GPU（n_gpu_layers={cfg_layers}，无法确认设备）"

    def to_smolagents_model(self, show_thinking: bool = True) -> Any:
        if self._llm is None:
            raise RuntimeError("Model has not been loaded. Call load() first.")
        return _LlamaCppSmolagentsModel(
            self._llm,
            max_new_tokens=self._config.max_tokens,
            show_thinking=show_thinking,
        )
