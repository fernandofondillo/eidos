"""Embeddings reales vía API — Fase 6.

Soporta múltiples providers de embeddings:
- MiniMax (embo-01) vía endpoint legacy /v1/embeddings
- OpenAI (text-embedding-3-small) vía endpoint compatible
- Stub (default, sin API) — bag-of-words determinista

Configuración vía .env:
  EMBEDDING_API_KEY=tu-key
  EMBEDDING_BASE_URL=https://api.minimax.io  (o https://api.openai.com/v1)
  EMBEDDING_MODEL=embo-01  (o text-embedding-3-small)
  EMBEDDING_PROVIDER=minimax  (o openai o stub)
  EMBEDDING_GROUP_ID=tu-group-id  (solo MiniMax, si es necesario)
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from eidos.memory.episodic import stub_embed, EMBEDDING_DIM
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class EmbedderBackend(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


class StubEmbedder:
    """Embeddings deterministas sin API (bag-of-words + L2 normalize)."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        return stub_embed(text, self._dim)


class OpenAIEmbedder:
    """Embeddings vía API compatible OpenAI (OpenAI, OpenRouter, etc.).

    Formato: POST {base_url}/embeddings
    Body: {"input": "text", "model": "text-embedding-3-small"}
    Response: {"data": [{"embedding": [...]}]}
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dim = dim
        self._timeout = timeout

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim

        payload = json.dumps({"input": text, "model": self._model}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                data = body.get("data", [])
                if not data:
                    logger.warning("openai_embedder_empty_response", text=text[:50])
                    return [0.0] * self._dim
                vec = data[0].get("embedding", [])
                # Ajustar dimensión
                if len(vec) > self._dim:
                    vec = vec[: self._dim]
                elif len(vec) < self._dim:
                    vec = list(vec) + [0.0] * (self._dim - len(vec))
                # L2 normalize
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]
                return vec
        except Exception as e:
            logger.warning("openai_embedder_error", error=str(e), text=text[:50])
            return stub_embed(text, self._dim)


class MiniMaxEmbedder:
    """Embeddings vía MiniMax (modelo embo-01).

    MiniMax NO es compatible con OpenAI. Usa formato legacy:
    POST {base_url}/v1/embeddings?GroupId={group_id}
    Body: {"model": "embo-01", "type": "query", "texts": ["text"]}
    Response: {"vectors": [[...]]}
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.minimax.io",
        model: str = "embo-01",
        group_id: str | None = None,
        dim: int = 1024,
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._group_id = group_id
        self._dim = dim
        self._timeout = timeout

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim

        # Construir URL con GroupId si está disponible
        url = f"{self._base_url}/v1/embeddings"
        if self._group_id:
            url += f"?GroupId={self._group_id}"

        # Formato MiniMax (NO OpenAI)
        payload = json.dumps({
            "model": self._model,
            "type": "query",  # "query" para búsquedas, "db" para indexar
            "texts": [text[:5000],],  # MiniMax limita a 5000 chars por texto
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))

                # MiniMax devuelve {"base_resp": {...}, "vectors": [[...]]}
                base_resp = body.get("base_resp", {})
                status = base_resp.get("status_code", -1)
                if status != 0:
                    logger.warning(
                        "minimax_embedder_api_error",
                        status=status,
                        msg=base_resp.get("status_msg", ""),
                        text=text[:50],
                    )
                    return stub_embed(text, self._dim)

                vectors = body.get("vectors", [])
                if not vectors:
                    logger.warning("minimax_embedder_empty_vectors", text=text[:50])
                    return stub_embed(text, self._dim)

                vec = vectors[0]

                # Ajustar dimensión
                if len(vec) > self._dim:
                    vec = vec[: self._dim]
                elif len(vec) < self._dim:
                    vec = list(vec) + [0.0] * (self._dim - len(vec))

                # L2 normalize
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]

                return vec

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.warning("minimax_embedder_http_error", code=e.code, body=body[:200])
            return stub_embed(text, self._dim)
        except Exception as e:
            logger.warning("minimax_embedder_error", error=str(e), text=text[:50])
            return stub_embed(text, self._dim)


def create_embedder_from_env() -> Any:
    """Crea el embedder basado en variables de entorno del .env.

    Lee:
    - EMBEDDING_PROVIDER: 'minimax' | 'openai' | 'stub' (default: stub)
    - EMBEDDING_API_KEY: API key del provider
    - EMBEDDING_BASE_URL: URL base (default: según provider)
    - EMBEDDING_MODEL: modelo (default: según provider)
    - EMBEDDING_GROUP_ID: Group ID de MiniMax (opcional)
    - EMBEDDING_DIM: dimensión del vector (default: según provider)

    Returns:
        Instancia de EmbedderBackend (StubEmbedder si no hay config).
    """
    provider = os.environ.get("EMBEDDING_PROVIDER", "stub").lower()
    api_key = os.environ.get("EMBEDDING_API_KEY", "")

    if provider == "stub" or not api_key:
        dim = int(os.environ.get("EMBEDDING_DIM", str(EMBEDDING_DIM)))
        logger.info("embedder_using_stub", dim=dim)
        return StubEmbedder(dim=dim)

    if provider == "minimax":
        base_url = os.environ.get("EMBEDDING_BASE_URL", "https://api.minimax.io")
        model = os.environ.get("EMBEDDING_MODEL", "embo-01")
        group_id = os.environ.get("EMBEDDING_GROUP_ID", "")
        dim = int(os.environ.get("EMBEDDING_DIM", "1024"))
        logger.info("embedder_using_minimax", model=model, dim=dim, group_id=bool(group_id))
        return MiniMaxEmbedder(
            api_key=api_key,
            base_url=base_url,
            model=model,
            group_id=group_id or None,
            dim=dim,
        )

    if provider == "openai":
        base_url = os.environ.get("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        dim = int(os.environ.get("EMBEDDING_DIM", "1536"))
        logger.info("embedder_using_openai", model=model, dim=dim)
        return OpenAIEmbedder(
            api_key=api_key,
            base_url=base_url,
            model=model,
            dim=dim,
        )

    # Fallback
    logger.warning("embedder_unknown_provider", provider=provider)
    return StubEmbedder()


__all__ = [
    "EmbedderBackend",
    "StubEmbedder",
    "OpenAIEmbedder",
    "MiniMaxEmbedder",
    "create_embedder_from_env",
]
