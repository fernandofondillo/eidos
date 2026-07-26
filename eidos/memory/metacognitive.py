"""Capa 5 — Memoria Metacognitiva (Lóbulo Frontal).

"Memoria sobre la memoria". Indexa los monólogos pasados para que EIDOS
pueda responder a: "¿por qué decidí X hace 3 días?".

Cada Monologue (Fase 1.1) ya se persiste como JSON en data/monologues/.
Esta capa indexa metadatos en SQLite (tabla `monologue_index`) para
búsqueda rápida por fecha, confianza, ruta, etc.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidos.core.monologue import Monologue
from eidos.memory.base import MemoryLayer
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class MetacognitiveMemory(MemoryLayer):
    """Capa 5: índice de monólogos para auto-evaluación."""

    layer_name = "metacognitive"

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    # ---------------- public API ----------------

    def store(self, monologue: Monologue, route_type: str | None = None) -> None:
        """Indexa un monólogo. Asume que el JSON ya está en disco
        (Monologue.to_json_file en Fase 1.1). Aquí solo registramos metadatos.
        """
        file_path = f"data/monologues/{monologue.id}.json"
        plan_json = json.dumps(monologue.plan, ensure_ascii=False)
        ts = monologue.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO monologue_index
                (id, ts, input_summary, hypothesis, plan, risk, confidence,
                 backend, file_path, route_type, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    monologue.id, ts, monologue.input_summary,
                    monologue.hypothesis, plan_json, monologue.risk,
                    monologue.confidence, monologue.backend,
                    file_path, route_type,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def set_outcome(self, monologue_id: str, outcome: str) -> None:
        """Anota el resultado real de la decisión (Fase 1.3 lo usa para
        reward signal y metacognición).
        """
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE monologue_index SET outcome = ? WHERE id = ?",
                (outcome, monologue_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, monologue_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, input_summary, hypothesis, plan, risk, "
                "confidence, backend, file_path, outcome, route_type "
                "FROM monologue_index WHERE id = ?",
                (monologue_id,),
            )
            r = cur.fetchone()
            return self._row_to_dict(r) if r else None
        finally:
            conn.close()

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, input_summary, hypothesis, plan, risk, "
                "confidence, backend, file_path, outcome, route_type "
                "FROM monologue_index ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def search_by_route(self, route_type: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, input_summary, hypothesis, plan, risk, "
                "confidence, backend, file_path, outcome, route_type "
                "FROM monologue_index WHERE route_type = ? "
                "ORDER BY ts DESC LIMIT ?",
                (route_type, limit),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def low_confidence(self, threshold: float = 0.5, limit: int = 20) -> list[dict[str, Any]]:
        """Devuelve decisiones pasadas con baja confianza — útiles para
        metacognición: ¿fallamos sistemáticamente en algún tipo de input?
        """
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, input_summary, hypothesis, plan, risk, "
                "confidence, backend, file_path, outcome, route_type "
                "FROM monologue_index WHERE confidence < ? "
                "ORDER BY confidence ASC LIMIT ?",
                (threshold, limit),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def clear(self) -> int:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM monologue_index")
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT COUNT(*), AVG(confidence), MIN(confidence), MAX(confidence) FROM monologue_index"
            )
            total, avg_conf, min_conf, max_conf = cur.fetchone()
            cur = conn.execute(
                "SELECT route_type, COUNT(*) FROM monologue_index GROUP BY route_type"
            )
            by_route = {row[0] or "unknown": row[1] for row in cur.fetchall()}
        finally:
            conn.close()
        return {
            "layer": self.layer_name,
            "total": total or 0,
            "avg_confidence": round(avg_conf, 3) if avg_conf is not None else None,
            "min_confidence": min_conf,
            "max_confidence": max_conf,
            "by_route": by_route,
        }

    # ---------------- internal ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    @staticmethod
    def _row_to_dict(r: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": r[0],
            "ts": r[1],
            "input_summary": r[2],
            "hypothesis": r[3],
            "plan": json.loads(r[4] or "[]"),
            "risk": r[5],
            "confidence": r[6],
            "backend": r[7],
            "file_path": r[8],
            "outcome": r[9],
            "route_type": r[10],
        }


__all__ = ["MetacognitiveMemory"]
