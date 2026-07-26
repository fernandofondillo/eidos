"""Router de Acción — Fase 1.1.

Tras el monólogo, EIDOS decide QUÉ hacer con él. El router clasifica
la ruta de acción. En Fase 1.1 las rutas son esquemáticas (no ejecutan
acciones reales todavía); se materializan en Fase 1.2+ con memoria y
en Fase 2 con Cortex Hub.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from eidos.core.monologue import Monologue


class RouteType(str, Enum):
    """Tipos de ruta que EIDOS puede tomar tras pensar."""

    RESPOND_DIRECT = "respond_direct"        # Tiene confianza, responde al usuario.
    SEARCH_MEMORY = "search_memory"          # Necesita recuperar contexto episódico/semántico.
    REQUEST_CLARIFICATION = "request_clarification"  # Confianza baja, pedir más info.
    DELEGATE_CORTEX = "delegate_cortex"      # Requiere inferencia LLM (Fase 2).
    DELEGATE_MESH = "delegate_mesh"          # Requiere otro EIDOS worker (Fase 4).
    SAFETY_BLOCK = "safety_block"            # Acción peligrosa detectada, abortar.


class Route(BaseModel):
    """Decisión del router."""

    route_type: RouteType
    reason: str = Field(..., min_length=1, max_length=500)
    # Payload para la siguiente fase. En Fase 1.1 solo es informativo.
    next_action_hint: str | None = None


class ActionRouter:
    """Decide la ruta de acción basándose en el monólogo + configuración.

    Reglas (neuro-simbólico: el monólogo propone, el router valida):
    1. confidence < threshold → REQUEST_CLARIFICATION.
    2. risk contiene 'safety' o 'peligro' → SAFETY_BLOCK.
    3. plan menciona "memoria episódica" → SEARCH_MEMORY.
    4. plan menciona "Cortex Hub" o "inferencia" → DELEGATE_CORTEX.
    5. default → RESPOND_DIRECT.
    """

    def __init__(self, confidence_threshold: float = 0.6) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0.0, 1.0]")
        self._threshold = confidence_threshold

    def decide(self, monologue: Monologue) -> Route:
        # 1. Confianza baja
        if monologue.confidence < self._threshold:
            return Route(
                route_type=RouteType.REQUEST_CLARIFICATION,
                reason=f"Confidence {monologue.confidence} < threshold {self._threshold}.",
                next_action_hint="Pedir al usuario más detalle o reformular.",
            )

        # 2. Riesgo de safety
        risk_lower = monologue.risk.lower()
        if any(w in risk_lower for w in ("safety", "peligro", "malicious", "block")):
            return Route(
                route_type=RouteType.SAFETY_BLOCK,
                reason=f"Risk signal in monologue: {monologue.risk}",
                next_action_hint="Abortar y notificar al usuario.",
            )

        # 3. Necesita memoria
        plan_blob = " ".join(monologue.plan).lower()
        if "memoria" in plan_blob or "memory" in plan_blob:
            return Route(
                route_type=RouteType.SEARCH_MEMORY,
                reason="Plan references memory retrieval.",
                next_action_hint="Consultar capas episódica/semántica (Fase 1.2).",
            )

        # 4. Necesita Cortex Hub
        if "cortex" in plan_blob or "inferencia" in plan_blob:
            return Route(
                route_type=RouteType.DELEGATE_CORTEX,
                reason="Plan references Cortex Hub inference.",
                next_action_hint="Invocar Cortex Hub con el modelo apropiado (Fase 2).",
            )

        # 5. Default
        return Route(
            route_type=RouteType.RESPOND_DIRECT,
            reason="Sufficient confidence and no delegation required.",
            next_action_hint="Generar respuesta directa al usuario.",
        )

    @property
    def confidence_threshold(self) -> float:
        return self._threshold


__all__ = ["ActionRouter", "Route", "RouteType"]
