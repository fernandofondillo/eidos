"""Capa 1 — Memoria Sensorial / Trabajo (Sensory / Working memory).

Contexto inmediato: los últimos N eventos (default 50).
Backend: deque en RAM + tabla `sensory_events` en SQLite para persistencia
entre reinicios (con LRU automático vía `window_size`).

Volátil por diseño: el consolidador (Fase 1.3) compacta lo importante
a la capa episódica y poda lo demás.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidos.memory.base import MemoryLayer
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class SensoryMemory(MemoryLayer):
    """Capa 1: contexto inmediato."""

    layer_name = "sensory"

    def __init__(self, db_path: Path, window_size: int = 50) -> None:
        self._db_path = db_path
        self._window_size = window_size
        self._buffer: deque[dict[str, Any]] = deque(maxlen=window_size)
        self._restore()

    # ---------------- public API ----------------

    def store(self, kind: str, content: str, metadata: dict[str, Any] | None = None) -> int:
        """Añade un evento sensorial. Devuelve el id en SQLite."""
        if not kind or not content:
            raise ValueError("kind and content are required")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        row = {"ts": ts, "kind": kind, "content": content, "metadata": metadata or {}}

        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO sensory_events(ts, kind, content, metadata) VALUES (?, ?, ?, ?)",
                (ts, kind, content, meta_json),
            )
            conn.commit()
            row_id = cur.lastrowid
        finally:
            conn.close()

        row["id"] = row_id
        self._buffer.append(row)
        self._prune_to_window(conn=None)
        return row_id or 0

    def recent(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Devuelve los últimos N eventos (más recientes primero)."""
        n = limit or len(self._buffer)
        return list(self._buffer)[-n:][::-1]

    def clear(self) -> int:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM sensory_events")
            conn.commit()
            deleted = cur.rowcount or 0
        finally:
            conn.close()
        self._buffer.clear()
        return deleted

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM sensory_events")
            total = cur.fetchone()[0]
        finally:
            conn.close()
        return {
            "layer": self.layer_name,
            "window_size": self._window_size,
            "buffered": len(self._buffer),
            "total_persisted": total,
        }

    # ---------------- internal ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _restore(self) -> None:
        """Carga los últimos `window_size` eventos al buffer en RAM."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, kind, content, metadata FROM sensory_events "
                "ORDER BY ts DESC LIMIT ?",
                (self._window_size,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        # Insertamos en orden inverso para que el deque mantenga orden cronológico
        for r in reversed(rows):
            self._buffer.append(
                {
                    "id": r[0],
                    "ts": r[1],
                    "kind": r[2],
                    "content": r[3],
                    "metadata": json.loads(r[4] or "{}"),
                }
            )

    def _prune_to_window(self, conn: sqlite3.Connection | None) -> None:
        """Mantiene solo `window_size` eventos en SQLite (LRU por ts)."""
        c = conn or self._conn()
        try:
            c.execute(
                "DELETE FROM sensory_events WHERE id NOT IN "
                "(SELECT id FROM sensory_events ORDER BY ts DESC LIMIT ?)",
                (self._window_size,),
            )
            c.commit()
        finally:
            if conn is None:
                c.close()


__all__ = ["SensoryMemory"]
