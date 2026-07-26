"""Capa 2 — Memoria Episódica (Hipocampo).

"Qué pasó y cuándo" — almacenamiento vectorial para recuperación
semántica de eventos pasados.

Backend v1: `sqlite-vec` (extensión SQLite, un único .db).
Backend upgrade path: LanceDB (Fase 2+, si escala).

Embeddings: en Fase 1.2 se usa un embedding **determinista** basado en
bag-of-words normalizado + hash. Permite probar la capa vectorial sin
GPU. En Fase 2 se sustituye por el embedding del Cortex Hub (Qwen2.5-3B
o modelo sentence-transformers pequeño).

Fase 2: el parámetro `embedder` permite inyectar cualquier backend que
implemente el protocolo EmbedderBackend. Si es None, usa stub_embed.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from eidos.memory.base import MemoryLayer
from eidos.utils.logging import get_logger

logger = get_logger(__name__)

# Dimensión del embedding stub. Debe coincidir con la del vec0 virtual table.
# En Fase 2, al usar embeddings reales, se puede recrear la tabla con otra dim.
EMBEDDING_DIM = 256


# ---------------------------------------------------------------------------
# Protocolo Embedder (idéntico al de eidos.cortex.embeddings, replicado aquí
# para evitar import circular en Fase 1.x cuando cortex no esté activo).
# ---------------------------------------------------------------------------


class _EmbedderLike(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


# ---------------------------------------------------------------------------
# Embedding stub — determinista, sin modelo. Para desarrollo Fase 1.x.
# ---------------------------------------------------------------------------


def stub_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Embedding determinista: bag-of-words hasheado a `dim` dimensiones,
    normalizado a norma L2 = 1.

    NO es un buen embedding semántico. Solo permite que la capa vectorial
    sea funcional y testeable sin GPU. Fase 2 lo sustituye.
    """
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    # Tokens simples (alfanuméricos lowercase, >=2 chars)
    cleaned = "".join(c if c.isalnum() else " " for c in text.lower())
    for tok in cleaned.split():
        if len(tok) < 2:
            continue
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(h, "big") % dim
        vec[idx] += 1.0
    # Normalización L2
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. Para fallback cuando sqlite-vec
    no está disponible."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Capa Episódica
# ---------------------------------------------------------------------------


class EpisodicMemory(MemoryLayer):
    """Capa 2: memoria episódica vectorial."""

    layer_name = "episodic"

    def __init__(
        self,
        db_path: Path,
        embedding_dim: int = EMBEDDING_DIM,
        max_events: int = 10000,
        embedder: _EmbedderLike | None = None,
    ) -> None:
        self._db_path = db_path
        self._dim = embedding_dim
        self._max_events = max_events
        # Fase 2: embedder inyectable. Si es None, usa stub_embed.
        # Si se provee, su dim prevalece sobre embedding_dim.
        self._embedder = embedder
        if embedder is not None:
            self._dim = embedder.dim
        self._vec_available = self._try_load_vec_extension()

    # ---------------- public API ----------------

    def store(
        self,
        kind: str,
        content: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> int:
        """Almacena un evento episódico con su embedding.

        Si `embedding` es None, se calcula con stub_embed o con el embedder
        inyectado (Fase 2).
        """
        if not kind or not content:
            raise ValueError("kind and content are required")
        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be in [0.0, 1.0]")

        emb = embedding or self._compute_embedding(content)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO episodic_events(ts, kind, content, embedding, importance, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, kind, content, json.dumps(emb), importance, meta_json),
            )
            conn.commit()
            row_id = cur.lastrowid
            if self._vec_available:
                self._vec_upsert(row_id, emb)
            self._prune_if_needed(conn)
        finally:
            conn.close()
        return row_id or 0

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Búsqueda por similitud. Devuelve top_k eventos con score."""
        if top_k <= 0:
            return []
        q_emb = self._compute_embedding(query)

        # Camino A: sqlite-vec (rápido, native)
        if self._vec_available:
            try:
                return self._vec_search(q_emb, top_k, min_score)
            except Exception as e:
                logger.warning("vec_search_fallback_to_bruteforce", error=str(e))

        # Camino B: bruteforce en Python (fallback si sqlite-vec no disponible)
        return self._bruteforce_search(q_emb, top_k, min_score)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, kind, content, importance, metadata "
                "FROM episodic_events ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def clear(self) -> int:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM episodic_events")
            deleted = cur.rowcount or 0
            conn.commit()
            if self._vec_available:
                try:
                    conn.execute("DELETE FROM episodic_vec")
                    conn.commit()
                except sqlite3.Error:
                    pass
        finally:
            conn.close()
        return deleted

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM episodic_events")
            total = cur.fetchone()[0]
        finally:
            conn.close()
        return {
            "layer": self.layer_name,
            "total": total,
            "max_events": self._max_events,
            "embedding_dim": self._dim,
            "vec_extension": self._vec_available,
        }

    # ---------------- internal: sqlite-vec ----------------

    def _compute_embedding(self, text: str) -> list[float]:
        """Usa el embedder inyectado (Fase 2) o stub_embed como fallback."""
        if self._embedder is not None:
            return self._embedder.embed(text)
        return stub_embed(text, self._dim)

    def _try_load_vec_extension(self) -> bool:
        """Intenta cargar sqlite-vec. Si no está disponible, degradamos a bruteforce."""
        try:
            import sqlite_vec  # type: ignore[import-not-found]

            # NO usar self._conn() aquí porque aún no tenemos _vec_available asignado.
            conn = sqlite3.connect(self._db_path)
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                # Crear tabla virtual vec0 si no existe
                conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS episodic_vec "
                    f"USING vec0(id INTEGER PRIMARY KEY, embedding float[{self._dim}])"
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except ImportError:
            logger.info("sqlite_vec_not_installed_using_bruteforce_fallback")
            return False
        except Exception as e:
            logger.warning("sqlite_vec_load_failed", error=str(e))
            return False

    def _vec_upsert(self, row_id: int, embedding: list[float]) -> None:
        conn = self._conn()
        try:
            # sqlite-vec no soporta UPSERT; delete+insert es el patrón canónico.
            conn.execute("DELETE FROM episodic_vec WHERE id = ?", (row_id,))
            conn.execute(
                "INSERT INTO episodic_vec(id, embedding) VALUES (?, ?)",
                (row_id, _vec_format(embedding)),
            )
            conn.commit()
        finally:
            conn.close()

    def _vec_search(
        self, q_emb: list[float], top_k: int, min_score: float
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT v.id, v.distance "
                "FROM episodic_vec v "
                "WHERE v.embedding MATCH ? "
                "ORDER BY v.distance "
                "LIMIT ?",
                (_vec_format(q_emb), top_k * 2),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        results: list[dict[str, Any]] = []
        for row_id, distance in rows:
            # sqlite-vec devuelve distancia L2; convertimos a similitud coseno aproximada.
            score = 1.0 - float(distance)
            if score < min_score:
                continue
            event = self._get_by_id(row_id)
            if event:
                event["score"] = round(score, 4)
                results.append(event)
            if len(results) >= top_k:
                break
        return results

    # ---------------- internal: bruteforce fallback ----------------

    def _bruteforce_search(
        self, q_emb: list[float], top_k: int, min_score: float
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, kind, content, embedding, importance, metadata FROM episodic_events"
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        scored: list[tuple[float, dict[str, Any]]] = []
        for r in rows:
            emb = json.loads(r[4] or "[]")
            score = _cosine(q_emb, emb)
            if score < min_score:
                continue
            scored.append((score, self._row_to_dict(r)))
        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        for score, ev in scored[:top_k]:
            ev["score"] = round(score, 4)
            out.append(ev)
        return out

    # ---------------- internal: utils ----------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        if self._vec_available:
            try:
                import sqlite_vec  # type: ignore[import-not-found]

                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
            except Exception:
                pass
        return conn

    def _get_by_id(self, row_id: int) -> dict[str, Any] | None:
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                "SELECT id, ts, kind, content, importance, metadata "
                "FROM episodic_events WHERE id = ?",
                (row_id,),
            )
            r = cur.fetchone()
            return self._row_to_dict(r) if r else None
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(r: tuple[Any, ...]) -> dict[str, Any]:
        """Convierte una fila SQL en dict.

        Acepta queries con columnas en este orden:
          (id, ts, kind, content, importance, metadata)            — sin embedding
          (id, ts, kind, content, embedding, importance, metadata) — con embedding
        """
        if len(r) == 6:
            # sin embedding
            return {
                "id": r[0],
                "ts": r[1],
                "kind": r[2],
                "content": r[3],
                "importance": r[4],
                "metadata": json.loads(r[5] or "{}"),
            }
        if len(r) >= 7:
            # con embedding
            return {
                "id": r[0],
                "ts": r[1],
                "kind": r[2],
                "content": r[3],
                "importance": r[5],
                "metadata": json.loads(r[6] or "{}"),
            }
        # fallback mínimo
        return {"id": r[0], "ts": r[1], "kind": r[2], "content": r[3]}

    def _prune_if_needed(self, conn: sqlite3.Connection) -> None:
        """LRU pruning: si excedemos max_events, eliminamos los de menor importancia."""
        cur = conn.execute("SELECT COUNT(*) FROM episodic_events")
        total = cur.fetchone()[0]
        if total <= self._max_events:
            return
        excess = total - self._max_events
        # Borrar los `excess` eventos con menor importance (y más antiguos como tiebreaker)
        cur = conn.execute(
            "SELECT id FROM episodic_events "
            "ORDER BY importance ASC, ts ASC LIMIT ?",
            (excess,),
        )
        ids_to_delete = [row[0] for row in cur.fetchall()]
        if not ids_to_delete:
            return
        placeholders = ",".join("?" * len(ids_to_delete))
        conn.execute(f"DELETE FROM episodic_events WHERE id IN ({placeholders})", ids_to_delete)
        if self._vec_available:
            try:
                conn.execute(f"DELETE FROM episodic_vec WHERE id IN ({placeholders})", ids_to_delete)
            except sqlite3.Error:
                pass
        conn.commit()
        logger.info("episodic_pruned", deleted=len(ids_to_delete))


def _vec_format(embedding: list[float]) -> bytes:
    """Serializa un embedding al formato binario que espera sqlite-vec."""
    import struct

    return struct.pack(f"{len(embedding)}f", *embedding)


__all__ = ["EpisodicMemory", "stub_embed", "EMBEDDING_DIM"]
