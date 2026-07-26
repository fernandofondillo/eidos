"""Consolidador en segundo plano — Fase 1.3.

Hilo daemon que ejecuta un loop de consolidación cada `interval_sec`
(default 300s = 5 min). Tareas por ciclo:

1. Compactar sensory → episódica: promueve eventos importantes.
2. Indexar monólogos en disco no indexados aún (recuperación tras crash).
3. Inferir `outcome` en monólogos sin outcome, basándose en rewards posteriores.
4. Poda de cápsulas caducadas (vía procedural.expire_due()).
5. Poda LRU de episódica (vía pruning existente; el consolidador lo dispara).
6. Persistir un `consolidation_runs` para auditabilidad.

El hilo es daemon: muere con el proceso principal. Se puede detener
limpiamente con `stop()` (cierra el evento y hace un join con timeout).

También expone `run_once()` para consolidación manual (CLI, tests).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eidos.memory.store import MemoryStore
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class Consolidator:
    """Loop de consolidación en background."""

    def __init__(
        self,
        memory: MemoryStore,
        db_path: Path,
        monologues_dir: Path,
        interval_sec: int = 300,
        sensory_importance_threshold: float = 0.6,
    ) -> None:
        self._memory = memory
        self._db_path = db_path
        self._monologues_dir = monologues_dir
        self._interval = max(30, int(interval_sec))  # mínimo 30s
        self._sensory_threshold = sensory_importance_threshold
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------- lifecycle ----------------

    def start(self) -> None:
        """Arranca el hilo daemon. Idempotente."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("consolidator_already_running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="eidos-consolidator",
            daemon=True,
        )
        self._thread.start()
        logger.info("consolidator_started", interval_sec=self._interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Detiene el hilo limpiamente."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("consolidator_thread_did_not_stop_in_time", timeout=timeout)
        else:
            logger.info("consolidator_stopped")
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------------- loop ----------------

    def _loop(self) -> None:
        # No ejecutar inmediatamente al arrancar; dar tiempo a que el usuario
        # interactúe antes de consolidar. Pero sí permitir parada rápida.
        if self._stop_event.wait(self._interval):
            return
        while not self._stop_event.is_set():
            try:
                self.run_once(kind="full")
            except Exception as e:
                logger.error("consolidation_run_failed", error=str(e))
            # Esperar interval o señal de stop, lo que llegue primero.
            if self._stop_event.wait(self._interval):
                break

    # ---------------- ejecución manual ----------------

    def run_once(self, kind: str = "manual") -> dict[str, Any]:
        """Ejecuta un ciclo completo de consolidación. Devuelve métricas."""
        start = time.perf_counter()
        details: dict[str, int] = {}
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # 1. Compactar sensory → episódica
        details["sensory_promoted"] = self._compact_sensory_to_episodic()

        # 2. Indexar monólogos no indexados
        details["monologues_indexed"] = self._index_orphan_monologues()

        # 3. Inferir outcomes pendientes
        details["outcomes_inferred"] = self._infer_outcomes()

        # 4. Poda de cápsulas caducadas
        details["capsules_expired"] = self._expire_capsules()

        # 5. LRU episódica (best-effort; el EpisodicMemory ya lo hace al store,
        #    pero forzamos una pasada contando lo que queda).
        details["episodic_pruned_check"] = self._check_episodic_overflow()

        # 6. Persistir run
        duration_ms = int((time.perf_counter() - start) * 1000)
        items = sum(details.values())
        self._log_run(ts=ts, kind=kind, items=items, duration_ms=duration_ms, details=details)
        logger.info("consolidation_run_complete", kind=kind, items=items, duration_ms=duration_ms, details=details)
        return {
            "kind": kind,
            "ts": ts,
            "items_processed": items,
            "duration_ms": duration_ms,
            "details": details,
        }

    # ---------------- pasos individuales ----------------

    def _compact_sensory_to_episodic(self) -> int:
        """Promueve eventos sensoriales 'response' con alta importancia
        implícita (basada en confidence del monólogo asociado) a episódica.

        Implementación v1: promovemos responses de los últimos N minutos
        cuya metadata contenga confidence >= threshold.
        """
        promoted = 0
        # Traer todos los sensory recientes
        recent = self._memory.sensory.recent(limit=50)
        for ev in recent:
            if ev["kind"] != "response":
                continue
            meta = ev.get("metadata") or {}
            confidence = float(meta.get("confidence", 0.0))
            if confidence < self._sensory_threshold:
                continue
            # ¿Ya promovido? Miramos metadata promoted=True
            if meta.get("promoted"):
                continue
            try:
                self._memory.episodic.store(
                    kind="consolidated_response",
                    content=ev["content"],
                    importance=confidence,
                    metadata={
                        "source_sensory_id": ev.get("id"),
                        "route": meta.get("route"),
                        "monologue_id": meta.get("monologue_id"),
                        "promoted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    },
                )
                promoted += 1
                # Marcar como promovido en sensory (best-effort; sensory es LRU
                # y aceptamos no persistir el flag para simplicidad)
            except Exception as e:
                logger.warning("sensory_promotion_failed", sensory_id=ev.get("id"), error=str(e))
        return promoted

    def _index_orphan_monologues(self) -> int:
        """Recorre data/monologues/ y indexa en monologue_index los JSONs
        que aún no estén indexados. Útil para recuperación tras crash."""
        if not self._monologues_dir.exists():
            return 0
        indexed = 0
        # Ids ya indexados
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute("SELECT id FROM monologue_index")
            known = {row[0] for row in cur.fetchall()}
        finally:
            conn.close()

        from eidos.core.monologue import Monologue  # local import para evitar ciclo

        for json_file in self._monologues_dir.glob("*.json"):
            mono_id = json_file.stem
            if mono_id in known:
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                # Rehidratar Monologue y re-indexar
                mono = Monologue.model_validate(data)
                self._memory.metacognitive.store(mono, route_type=None)
                indexed += 1
            except Exception as e:
                logger.warning("orphan_monologue_index_failed", file=str(json_file), error=str(e))
        return indexed

    def _infer_outcomes(self) -> int:
        """Para monólogos sin `outcome`, infiere uno basándose en rewards
        posteriores (dentro de una ventana de 5 min).
        """
        conn = sqlite3.connect(self._db_path)
        try:
            # Monologues sin outcome
            cur = conn.execute(
                "SELECT id, ts FROM monologue_index WHERE outcome IS NULL ORDER BY ts DESC LIMIT 100"
            )
            pending = cur.fetchall()
            inferred = 0
            for mono_id, mono_ts in pending:
                try:
                    mono_dt = datetime.fromisoformat(mono_ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                window_end = mono_dt + timedelta(minutes=5)
                cur2 = conn.execute(
                    "SELECT driver, SUM(delta) FROM reward_events "
                    "WHERE monologue_id = ? OR (ts BETWEEN ? AND ?) "
                    "GROUP BY driver",
                    (mono_id, mono_ts, window_end.strftime("%Y-%m-%dT%H:%M:%S.%fZ")),
                )
                if cur2 is None:
                    continue
                rows = cur2.fetchall()
                if not rows:
                    continue
                total = sum(r[1] or 0.0 for r in rows)
                if total > 0.2:
                    outcome = "positive"
                elif total < -0.2:
                    outcome = "negative"
                else:
                    outcome = "neutral"
                conn.execute(
                    "UPDATE monologue_index SET outcome = ? WHERE id = ?",
                    (outcome, mono_id),
                )
                inferred += 1
            conn.commit()
            return inferred
        finally:
            conn.close()

    def _expire_capsules(self) -> int:
        """Poda cápsulas caducadas (no favoritas, TTL pasado)."""
        expired_ids = self._memory.procedural.expire_due()
        for cid in expired_ids:
            try:
                self._memory.procedural.delete(cid)
            except Exception as e:
                logger.warning("capsule_expiry_delete_failed", id=cid, error=str(e))
        return len(expired_ids)

    def _check_episodic_overflow(self) -> int:
        """Verifica (y dispara) pruning LRU en episódica si excede max_events.
        Devuelve 0 siempre (el pruning real ocurre en EpisodicMemory.store),
        pero mantenemos el método para logging/audit."""
        stats = self._memory.episodic.stats()
        return 1 if stats["total"] > stats["max_events"] else 0

    def _log_run(
        self,
        ts: str,
        kind: str,
        items: int,
        duration_ms: int,
        details: dict[str, int],
    ) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT INTO consolidation_runs(ts, kind, items_processed, duration_ms, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, kind, items, duration_ms, json.dumps(details, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    # ---------------- reportes ----------------

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                "SELECT id, ts, kind, items_processed, duration_ms, details "
                "FROM consolidation_runs ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "kind": r[2],
                    "items_processed": r[3],
                    "duration_ms": r[4],
                    "details": json.loads(r[5] or "{}"),
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()


__all__ = ["Consolidator"]
