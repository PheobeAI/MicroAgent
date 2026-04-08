# core/model.py
from abc import ABC, abstractmethod
from typing import Any

from core.config import ModelConfig

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore

try:
    from smolagents import LlamaCppModel
except ImportError:
    LlamaCppModel = None  # type: ignore


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
        return LlamaCppModel(self._llm, max_new_tokens=self._config.max_tokens)
