"""Embeddings reales — Fase 2.

Reemplaza stub_embed en EpisodicMemory cuando el Cortex Hub está activo.
Usa un modelo de embeddings pequeño (ej. BGE-small-en o multilingual).

Diseño:
- EmbedderBackend protocol: cualquier backend lo implementa.
- StubEmbedder: wrapper sobre stub_embed (compatibilidad hacia atrás).
- LlamaCppEmbedder: usa llama-cpp-python con modelo de embeddings.
- Lazy import + inyectable para tests.
"""

from __future__ import annotations

from typing import Any, Protocol

from eidos.memory.episodic import stub_embed
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------


class EmbedderBackend(Protocol):
    """Contrato para cualquier backend de embeddings."""

    @property
    def dim(self) -> int:
        """Dimensión de los vectores producidos."""
        ...

    def embed(self, text: str) -> list[float]:
        """Devuelve un vector L2-normalizado."""
        ...


# ---------------------------------------------------------------------------
# StubEmbedder — wrapper sobre stub_embed (default, sin GPU)
# ---------------------------------------------------------------------------


class StubEmbedder:
    """Wrapper sobre stub_embed para cumplir EmbedderBackend."""

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        return stub_embed(text, self._dim)


# ---------------------------------------------------------------------------
# LlamaCppEmbedder — embeddings reales con llama-cpp-python
# ---------------------------------------------------------------------------


class LlamaCppEmbedder:
    """Backend de embeddings basado en llama-cpp-python.

    Requiere un modelo de embeddings GGUF (ej. bge-small-en-v1.5-q8_0.gguf).

    Para tests se puede inyectar un `client` que implemente `embed(text) -> list[float]`.
    """

    def __init__(
        self,
        model_path: str,
        dim: int = 384,
        n_ctx: int = 512,
        n_gpu_layers: int = -1,
        client: Any = None,
    ) -> None:
        self._model_path = model_path
        self._dim = dim
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers

        if client is not None:
            self._client = client
            self._owns = False
        else:
            self._client = self._load_real()
            self._owns = True

    def _load_real(self) -> Any:
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python no está instalado. "
                "Instala con: CMAKE_ARGS='-DGGML_METAL=on' uv sync --extra cortex"
            ) from e
        logger.info("embedder_loading", model=self._model_path, dim=self._dim)
        return Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            embedding=True,
            verbose=False,
        )

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim
        # llama_cpp.Llama tiene método .create_embedding(text) -> {"embedding": [...]}
        if hasattr(self._client, "create_embedding"):
            result = self._client.create_embedding([text])
            vec = result.get("data", [{}])[0].get("embedding", [])
        elif hasattr(self._client, "embed"):  # mock-friendly
            vec = self._client.embed(text)
        else:
            raise RuntimeError("LlamaCppEmbedder client has no embed/create_embedding method")

        if len(vec) != self._dim:
            # Truncar o paddear para mantener consistencia con la tabla vec0
            if len(vec) > self._dim:
                vec = vec[: self._dim]
            else:
                vec = list(vec) + [0.0] * (self._dim - len(vec))

        # L2 normalize
        import math

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def close(self) -> None:
        if self._owns:
            self._client = None


__all__ = ["EmbedderBackend", "StubEmbedder", "LlamaCppEmbedder"]
