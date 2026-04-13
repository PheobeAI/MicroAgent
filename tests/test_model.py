# tests/test_model.py
from unittest.mock import MagicMock, patch
from core.config import ModelConfig
from core.model import LlamaCppBackend, _LlamaCppSmolagentsModel, _parse_gemma_tool_calls


def test_load_calls_llama_with_correct_params():
    config = ModelConfig(
        path="./model.gguf",
        n_gpu_layers=-1,
        n_threads=6,
        n_ctx=4096,
    )
    with patch("core.model.Llama") as mock_llama:
        backend = LlamaCppBackend(config)
        backend.load()
        mock_llama.assert_called_once_with(
            model_path="./model.gguf",
            n_gpu_layers=-1,
            n_threads=6,
            n_ctx=4096,
            flash_attn=True,
            verbose=False,
        )


def test_to_smolagents_model_returns_wrapped_model():
    config = ModelConfig()
    with patch("core.model.Llama") as mock_llama:
        mock_instance = MagicMock()
        mock_llama.return_value = mock_instance
        backend = LlamaCppBackend(config)
        backend.load()

    result = backend.to_smolagents_model()
    assert isinstance(result, _LlamaCppSmolagentsModel)
    assert result._llm is mock_instance
    assert result._max_new_tokens == config.max_tokens


def test_get_memory_usage_returns_float():
    config = ModelConfig()
    backend = LlamaCppBackend(config)
    with patch("psutil.Process") as mock_proc:
        mock_proc.return_value.memory_info.return_value.rss = 2 * 1024 ** 3
        usage = backend.get_memory_usage_gb()
    assert abs(usage - 2.0) < 0.01


def test_parse_gemma_tool_calls_no_args():
    content = '<|tool_call>call:system_info{}<tool_call|><|tool_response><eos>'
    calls = _parse_gemma_tool_calls(content)
    assert calls is not None and len(calls) == 1
    assert calls[0].function.name == "system_info"
    assert calls[0].function.arguments == {}


def test_parse_gemma_tool_calls_with_string_arg():
    content = '<|tool_call>call:web_search{query:<|"|>Python 最新版本<|"|>}<tool_call|>'
    calls = _parse_gemma_tool_calls(content)
    assert calls is not None and len(calls) == 1
    assert calls[0].function.name == "web_search"
    assert calls[0].function.arguments == {"query": "Python 最新版本"}


def test_parse_gemma_tool_calls_multi_arg():
    content = '<|tool_call>call:find_files{path:<|"|>.<|"|>, pattern:<|"|>*.py<|"|>}<tool_call|>'
    calls = _parse_gemma_tool_calls(content)
    assert calls is not None and len(calls) == 1
    assert calls[0].function.arguments == {"path": ".", "pattern": "*.py"}


def test_parse_gemma_tool_calls_value_with_colon():
    content = '<|tool_call>call:web_search{query:<|"|>https://example.com/foo:bar<|"|>}<tool_call|>'
    calls = _parse_gemma_tool_calls(content)
    assert calls[0].function.arguments == {"query": "https://example.com/foo:bar"}


def test_parse_gemma_tool_calls_returns_none_for_json():
    # Standard JSON format should NOT be parsed by this function
    content = 'Action:\n{"name": "system_info"}'
    assert _parse_gemma_tool_calls(content) is None
