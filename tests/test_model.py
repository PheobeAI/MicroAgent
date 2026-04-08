# tests/test_model.py
from unittest.mock import MagicMock, patch
from core.config import ModelConfig
from core.model import LlamaCppBackend


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
            verbose=False,
        )


def test_to_smolagents_model_returns_wrapped_model():
    config = ModelConfig()
    with patch("core.model.Llama") as mock_llama:
        mock_instance = MagicMock()
        mock_llama.return_value = mock_instance
        backend = LlamaCppBackend(config)
        backend.load()

    with patch("core.model.LlamaCppModel") as mock_wrapper:
        mock_wrapper.return_value = MagicMock()
        result = backend.to_smolagents_model()
        mock_wrapper.assert_called_once_with(mock_instance, max_new_tokens=config.max_tokens)
        assert result is mock_wrapper.return_value


def test_get_memory_usage_returns_float():
    config = ModelConfig()
    backend = LlamaCppBackend(config)
    with patch("psutil.Process") as mock_proc:
        mock_proc.return_value.memory_info.return_value.rss = 2 * 1024 ** 3
        usage = backend.get_memory_usage_gb()
    assert abs(usage - 2.0) < 0.01
