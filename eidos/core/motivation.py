"""Motivación Intrínseca — Fase 1.3.

EIDOS no responde solo a estímulos externos; tiene un reward signal
interno que modela tres drives motivacionales:

1. Curiosidad / Reducción de incertidumbre — subir confianza = recompensa.
2. Reutilización de cápsulas — invocar una cápsula exitosamente = recompensa.
3. Satisfacción del usuario (heurística) — turnos sin corrección = recompensa,
   detección de "no/mal/incorrecto" = penalización.

El reward_signal total ([-1, +1]) se persiste en `reward_events` para
que la capa metacognitiva pueda auditar por qué EIDOS favoreció ciertas
estrategias. El consolidador (Fase 1.3) usa estos eventos para inferir
`outcome` en monólogos sin outcome explícito.

El reward NO controla el comportamiento del núcleo en Fase 1.3 (eso es
aprendizaje por refuerzo, fuera de alcance). Solo:
- Sube `importance` de eventos episódicos asociados a rewards positivos.
- Cuenta usos en cápsulas reutilizadas.
- Sirve de input al consolidador.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from eidos.memory.procedural import ProceduralMemory
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class RewardDriver(str, Enum):
    """Drivers motivacionales de EIDOS."""

    CURIOSITY = "curiosity"                    # reducción de incertidumbre
    CAPSULE_REUSE = "capsule_reuse"            # invocación exitosa de cápsula
    USER_SATISFACTION = "user_satisfaction"    # heurística de satisfacción


# Pesos por driver — suma <= 1.0 para mantener reward en [-1, +1] aprox.
_DRIVER_WEIGHTS: dict[RewardDriver, float] = {
    RewardDriver.CURIOSITY: 0.3,
    RewardDriver.CAPSULE_REUSE: 0.4,
    RewardDriver.USER_SATISFACTION: 0.3,
}

# Palabras/frases que indican insatisfacción (heurística simple, multiidioma).
_NEGATIVE_SIGNALS = frozenset(
    {
        # ES
        "no", "mal", "incorrecto", "error", "equivocado", "mal hecho",
        "no me gusta", "fallo", "malo", "terrible", "peor",
        # EN
        "wrong", "bad", "incorrect", "nope", "terrible", "worse", "fail",
    }
)


class MotivationModule:
    """Genera y persiste rewards internos. No controla comportamiento;
    solo mide y feedbacka."""

    def __init__(
        self,
        db_path: Path,
        procedural: ProceduralMemory | None = None,
        confidence_window: int = 5,
        satisfaction_window: int = 3,
    ) -> None:
        self._db_path = db_path
        self._procedural = procedural
        # Memoria rolling para heurísticas (no se persiste; se reinicia con el proceso)
        self._confidence_history: deque[float] = deque(maxlen=confidence_window)
        self._satisfaction_window = satisfaction_window
        # Últimos N inputs del usuario (para detectar racha sin correcciones)
        self._recent_user_inputs: deque[str] = deque(maxlen=satisfaction_window)
        self._total_reward: float = 0.0

    # ---------------- API pública ----------------

    def observe_confidence(self, confidence: float, monologue_id: str | None = None) -> float:
        """Registra la confianza de un monólogo. Genera reward de curiosidad
        si la confianza supera la media móvil reciente por un margen."""
        avg = (
            sum(self._confidence_history) / len(self._confidence_history)
            if self._confidence_history
            else 0.0
        )
        self._confidence_history.append(confidence)

        # Reward solo si hay historial y la confianza sube significativamente.
        if len(self._confidence_history) >= 2 and confidence > avg + 0.1:
            delta = _DRIVER_WEIGHTS[RewardDriver.CURIOSITY]
            self._log_reward(
                driver=RewardDriver.CURIOSITY,
                delta=delta,
                monologue_id=monologue_id,
                metadata={"confidence": confidence, "avg_recent": round(avg, 3)},
            )
            return delta
        return 0.0

    def reward_capsule_use(self, capsule_id: str, monologue_id: str | None = None) -> float:
        """Llamar cuando una cápsula se invoca exitosamente.
        Incrementa `uses` en ProceduralMemory y registra reward."""
        if self._procedural is not None:
            try:
                self._procedural.mark_used(capsule_id)
            except Exception as e:
                logger.warning("capsule_mark_used_failed", capsule_id=capsule_id, error=str(e))

        delta = _DRIVER_WEIGHTS[RewardDriver.CAPSULE_REUSE]
        self._log_reward(
            driver=RewardDriver.CAPSULE_REUSE,
            delta=delta,
            monologue_id=monologue_id,
            metadata={"capsule_id": capsule_id},
        )
        return delta

    def observe_user_input(self, user_input: str, monologue_id: str | None = None) -> float:
        """Heurística de satisfacción del usuario. Detecta:
        - Señales negativas explícitas → penalización fuerte.
        - Racha de N turnos sin señales negativas → recompensa acumulada.
        """
        text_lower = user_input.lower().strip()
        self._recent_user_inputs.append(user_input)

        # ¿Señal negativa en este turno?
        has_negative = any(neg in text_lower for neg in _NEGATIVE_SIGNALS)
        if has_negative:
            delta = -0.5  # penalización clara pero no destructiva
            self._log_reward(
                driver=RewardDriver.USER_SATISFACTION,
                delta=delta,
                monologue_id=monologue_id,
                metadata={"signal": "negative_detected", "input_preview": user_input[:80]},
            )
            # Resetear la racha: empezamos de cero tras una corrección
            self._recent_user_inputs.clear()
            return delta

        # ¿Racha completa sin señales negativas?
        if len(self._recent_user_inputs) >= self._satisfaction_window:
            delta = _DRIVER_WEIGHTS[RewardDriver.USER_SATISFACTION]
            self._log_reward(
                driver=RewardDriver.USER_SATISFACTION,
                delta=delta,
                monologue_id=monologue_id,
                metadata={
                    "signal": "streak_complete",
                    "streak_len": len(self._recent_user_inputs),
                },
            )
            # Consumir la racha para no premiar dos veces la misma ventana
            self._recent_user_inputs.clear()
            return delta
        return 0.0

    def total_reward(self) -> float:
        """Reward acumulado en esta sesión (no persistente entre reinicios)."""
        return round(self._total_reward, 4)

    def recent_rewards(self, limit: int = 20) -> list[dict[str, Any]]:
        """Últimos N rewards persistidos (de cualquier sesión)."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, ts, monologue_id, driver, delta, total, metadata "
                "FROM reward_events ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "monologue_id": r[2],
                    "driver": r[3],
                    "delta": r[4],
                    "total": r[5],
                    "metadata": json.loads(r[6] or "{}"),
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def rewards_by_driver(self) -> dict[str, dict[str, float]]:
        """Agregados por driver: total delta, count. Útil para stats."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT driver, COUNT(*), SUM(delta) FROM reward_events GROUP BY driver"
            )
            return {
                row[0]: {"count": row[1], "total_delta": round(row[2] or 0.0, 4)}
                for row in cur.fetchall()
            }
        finally:
            conn.close()

    def stats(self) -> dict[str, Any]:
        return {
            "module": "motivation",
            "session_total_reward": self.total_reward(),
            "by_driver": self.rewards_by_driver(),
            "confidence_window_size": len(self._confidence_history),
            "satisfaction_streak": len(self._recent_user_inputs),
            "satisfaction_window": self._satisfaction_window,
        }

    # ---------------- internal ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _log_reward(
        self,
        driver: RewardDriver,
        delta: float,
        monologue_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._total_reward += delta
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO reward_events(ts, monologue_id, driver, delta, total, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    monologue_id,
                    driver.value,
                    round(delta, 4),
                    round(self._total_reward, 4),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            "reward_logged",
            driver=driver.value,
            delta=round(delta, 4),
            total=round(self._total_reward, 4),
        )


__all__ = ["MotivationModule", "RewardDriver"]
