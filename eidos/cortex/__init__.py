"""Cortex Hub — sentidos periféricos de EIDOS (Fase 2).

Componentes:
- manager:        descarga y catálogo de modelos GGUF/ONNX locales.
- llama_backend:  backend de monólogo con llama-cpp-python + GBNF.
- embeddings:     embeddings reales (reemplaza stub_embed).
- privacy:        PrivacyFilter para redactar PII antes de API externa.
- api_fallback:   fallback a APIs OpenAI-compatibles con privacy filter.
- hub:            CortexHub facade con lock singleton-virtual-ready.
"""

from eidos.cortex.api_fallback import APIFallbackBackend
from eidos.cortex.embeddings import EmbedderBackend, LlamaCppEmbedder, StubEmbedder
from eidos.cortex.hub import CortexHub, CortexLock
from eidos.cortex.llama_backend import LlamaClient, LlamaCppBackend
from eidos.cortex.manager import ModelInfo, ModelManager, ModelStatus
from eidos.cortex.privacy import FilterResult, PrivacyFilter

__all__ = [
    "CortexHub",
    "CortexLock",
    "ModelManager",
    "ModelInfo",
    "ModelStatus",
    "LlamaCppBackend",
    "LlamaClient",
    "APIFallbackBackend",
    "EmbedderBackend",
    "StubEmbedder",
    "LlamaCppEmbedder",
    "PrivacyFilter",
    "FilterResult",
]
