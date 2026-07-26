"""CortexHub — Fase 2 + Fase 4.

Facade unificada para los "sentidos periféricos" de EIDOS:
- ModelManager (catálogo de modelos)
- LlamaCppBackend (monólogo con LLM local)
- LlamaCppEmbedder (embeddings reales)
- APIFallbackBackend (fallback externo con privacy filter)

Singleton-virtual-ready (Fase 4):
- try_acquire_lock(role, ttl_sec) → bool
  - Si mesh_coordinator es None: file lock local (fcntl, Fase 2).
  - Si mesh_coordinator está configurado: pide resource_token MESH distribuido.
- La API pública es la misma; solo cambia la implementación interna.
"""

from __future__ import annotations

import fcntl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eidos.cortex.embeddings import EmbedderBackend, StubEmbedder
from eidos.cortex.llama_backend import LlamaCppBackend, LlamaClient
from eidos.cortex.manager import ModelManager, ModelStatus
from eidos.cortex.privacy import PrivacyFilter
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lock handle (Fase 2: file lock; Fase 4: MESH resource token)
# ---------------------------------------------------------------------------


@dataclass
class CortexLock:
    """Handle del lock del CortexHub."""

    role: str
    acquired_at: float
    ttl_sec: float
    _fd: Any = None  # file descriptor del lock (Fase 2)
    _mesh_token_id: str | None = None  # MESH resource token (Fase 4)

    def is_expired(self) -> bool:
        return time.time() > self.acquired_at + self.ttl_sec

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                self._fd.close()
                self._fd = None
            except Exception as e:
                logger.warning("cortex_lock_release_failed", error=str(e))


# ---------------------------------------------------------------------------
# CortexHub
# ---------------------------------------------------------------------------


class CortexHub:
    """Facade de los sentidos periféricos de EIDOS."""

    def __init__(
        self,
        model_manager: ModelManager,
        lock_path: Path | None = None,
        privacy_filter: PrivacyFilter | None = None,
        mesh_coordinator: Any = None,
    ) -> None:
        """Args:
            mesh_coordinator: si es None, usa fcntl local (Fase 2).
                Si está configurado, usa resource_token MESH distribuido (Fase 4).
        """
        self._mm = model_manager
        self._lock_path = lock_path or Path("/tmp/eidos.cortex.lock")
        self._privacy = privacy_filter or PrivacyFilter()
        self._mesh = mesh_coordinator
        self._current_lock: CortexLock | None = None
        # Caches para no recargar modelos en cada call
        self._monologue_backend: LlamaCppBackend | Any = None
        self._embedder: EmbedderBackend | None = None

    # ---------------- Singleton-virtual lock ----------------

    def try_acquire_lock(self, role: str = "primary", ttl_sec: float = 30.0) -> bool:
        """Intenta adquirir el lock del CortexHub.

        Fase 2 (mesh_coordinator=None): file lock local exclusivo.
        Fase 4 (mesh_coordinator set): resource_token MESH distribuido.
        """
        # ¿Ya tenemos lock activo y vigente?
        if self._current_lock is not None and not self._current_lock.is_expired():
            return True

        # ¿Lock activo pero expirado? Liberar primero
        if self._current_lock is not None:
            self._release_current_lock()
            self._current_lock = None

        # Fase 4: pedir token MESH
        if self._mesh is not None:
            return self._acquire_mesh_lock(role, ttl_sec)

        # Fase 2: fcntl local
        return self._acquire_local_lock(role, ttl_sec)

    def _acquire_local_lock(self, role: str, ttl_sec: float) -> bool:
        """Fase 2: fcntl.flock local exclusivo."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = open(self._lock_path, "w")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(f"{role}\n")
            fd.flush()
        except BlockingIOError:
            fd.close()
            logger.warning("cortex_lock_busy", path=str(self._lock_path))
            return False
        except OSError as e:
            logger.warning("cortex_lock_unavailable_degraded", error=str(e))
            fd.close()
            self._current_lock = CortexLock(
                role=role, acquired_at=time.time(), ttl_sec=ttl_sec
            )
            return True

        self._current_lock = CortexLock(
            role=role,
            acquired_at=time.time(),
            ttl_sec=ttl_sec,
            _fd=fd,
        )
        logger.info("cortex_lock_acquired_local", role=role, ttl=ttl_sec)
        return True

    def _acquire_mesh_lock(self, role: str, ttl_sec: float) -> bool:
        """Fase 4: pide resource_token 'cortex' al arbitrator MESH."""
        try:
            token = self._mesh.acquire_resource(
                resource="cortex",
                ttl_sec=ttl_sec,
                metadata={"role": role},
            )
            if token is None:
                logger.warning("cortex_lock_mesh_denied", resource="cortex")
                return False
            self._current_lock = CortexLock(
                role=role,
                acquired_at=time.time(),
                ttl_sec=ttl_sec,
                _mesh_token_id=token.token_id,
            )
            logger.info(
                "cortex_lock_acquired_mesh",
                role=role,
                ttl=ttl_sec,
                token_id=token.token_id,
            )
            return True
        except Exception as e:
            logger.error("cortex_lock_mesh_failed", error=str(e))
            return False

    def _release_current_lock(self) -> None:
        """Libera el lock actual (local o MESH)."""
        if self._current_lock is None:
            return
        # Si hay mesh_token_id, liberar vía MESH
        if self._current_lock._mesh_token_id is not None and self._mesh is not None:
            try:
                self._mesh.release_resource(self._current_lock._mesh_token_id)
            except Exception as e:
                logger.warning("cortex_lock_mesh_release_failed", error=str(e))
        # Si hay fd (Fase 2), liberar file lock
        if self._current_lock._fd is not None:
            self._current_lock.release()
        self._current_lock = None
        logger.info("cortex_lock_released")

    def release_lock(self) -> None:
        self._release_current_lock()

    def has_lock(self) -> bool:
        return self._current_lock is not None and not self._current_lock.is_expired()

    # ---------------- Backend de monólogo ----------------

    def get_monologue_backend(
        self,
        model_id: str | None = None,
        max_plan_steps: int = 5,
        client: LlamaClient | None = None,
    ) -> Any:
        """Devuelve un MonologueBackend listo para usar, o None si no hay
        ningún modelo disponible."""
        if model_id is None:
            candidates = self._mm.list_by_purpose("monologue")
            ready = [m for m in candidates if m.status == ModelStatus.READY.value]
            if not ready:
                logger.info("cortex_no_monologue_model_available")
                return None
            model_id = ready[0].id

        if self._monologue_backend is not None and getattr(self._monologue_backend, "_model_id", None) == model_id:
            return self._monologue_backend

        info = self._mm.get(model_id)
        if info is None or info.status != ModelStatus.READY.value:
            logger.warning("cortex_model_not_ready", model_id=model_id, status=info.status if info else None)
            return None

        path = self._mm.resolve_path(model_id)
        if path is None or not path.exists():
            logger.error("cortex_model_file_missing", model_id=model_id)
            return None

        backend = LlamaCppBackend(
            model_path=str(path),
            max_plan_steps=max_plan_steps,
            client=client,
        )
        backend._model_id = model_id  # type: ignore[attr-defined]
        self._monologue_backend = backend
        return backend

    # ---------------- Embedder ----------------

    def get_embedder(
        self,
        model_id: str | None = None,
        dim: int = 256,
        client: Any = None,
    ) -> EmbedderBackend:
        """Devuelve un EmbedderBackend. Si hay modelo de embeddings READY,
        usa LlamaCppEmbedder; si no, degrada a StubEmbedder."""
        if model_id is None:
            candidates = self._mm.list_by_purpose("embedding")
            ready = [m for m in candidates if m.status == ModelStatus.READY.value]
            if not ready:
                return StubEmbedder(dim=dim)
            model_id = ready[0].id

        if self._embedder is not None and getattr(self._embedder, "_model_id", None) == model_id:
            return self._embedder

        info = self._mm.get(model_id)
        if info is None or info.status != ModelStatus.READY.value:
            return StubEmbedder(dim=dim)

        path = self._mm.resolve_path(model_id)
        if path is None or not path.exists():
            return StubEmbedder(dim=dim)

        from eidos.cortex.embeddings import LlamaCppEmbedder

        embedder = LlamaCppEmbedder(
            model_path=str(path),
            dim=dim,
            client=client,
        )
        embedder._model_id = model_id  # type: ignore[attr-defined]
        self._embedder = embedder
        return embedder

    # ---------------- Privacy filter (público) ----------------

    @property
    def privacy_filter(self) -> PrivacyFilter:
        return self._privacy

    # ---------------- Lifecycle ----------------

    def close(self) -> None:
        """Libera todos los recursos."""
        if self._monologue_backend is not None:
            try:
                self._monologue_backend.close()
            except Exception as e:
                logger.warning("cortex_monologue_backend_close_failed", error=str(e))
            self._monologue_backend = None
        if self._embedder is not None:
            try:
                if hasattr(self._embedder, "close"):
                    self._embedder.close()
            except Exception as e:
                logger.warning("cortex_embedder_close_failed", error=str(e))
            self._embedder = None
        self.release_lock()

    def stats(self) -> dict[str, Any]:
        return {
            "module": "cortex_hub",
            "lock_path": str(self._lock_path),
            "has_lock": self.has_lock(),
            "mesh_enabled": self._mesh is not None,
            "monologue_backend_active": self._monologue_backend is not None,
            "embedder_active": self._embedder is not None,
            "models": self._mm.stats(),
        }


__all__ = ["CortexHub", "CortexLock"]
