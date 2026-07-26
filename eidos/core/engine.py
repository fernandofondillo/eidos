"""EidosCore — orquestador principal del núcleo cognitivo. Fase 1.1.

Flujo mínimo:
    user_input → MonologueGenerator → Monologue
               → ActionRouter        → Route
               → (placeholder)       → Response

En Fase 1.1, la Response es un template construido a partir del monólogo
y la ruta. La capa de NLG real llega en Fase 2 (Cortex Hub).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.router import ActionRouter, Route
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class Response(BaseModel):
    """Respuesta final de EIDOS al usuario."""

    text: str = Field(..., min_length=1)
    monologue_id: str
    route_type: str
    confidence: float


class EidosCore:
    """El núcleo cognitivo de EIDOS.

    En Fase 1.1 es un orquestador mínimo pero funcional:
    piensa (monologue) → decide ruta (router) → responde (template).
    """

    def __init__(
        self,
        monologue_backend: str = "stub",
        confidence_threshold: float = 0.6,
        monologues_dir: Path | None = None,
        max_plan_steps: int = 5,
    ) -> None:
        self._generator = MonologueGenerator(
            backend=monologue_backend,
            monologues_dir=monologues_dir,
            max_plan_steps=max_plan_steps,
        )
        self._router = ActionRouter(confidence_threshold=confidence_threshold)
        self._monologues_dir = monologues_dir
        logger.info(
            "eidos_core_init",
            backend=monologue_backend,
            threshold=confidence_threshold,
            persist=bool(monologues_dir),
        )

    def think_and_respond(self, user_input: str, context: str | None = None) -> Response:
        """Pipeline completo: input → monólogo → ruta → respuesta."""
        logger.debug("eidos_input", length=len(user_input))

        # 1. Pensar
        monologue = self._generator.generate(user_input, context)
        logger.info(
            "eidos_monologue",
            id=monologue.id,
            confidence=monologue.confidence,
            backend=monologue.backend,
        )

        # 2. Decidir ruta
        route = self._router.decide(monologue)
        logger.info("eidos_route", route=route.route_type.value, reason=route.reason)

        # 3. Responder (template; NLG real en Fase 2)
        text = self._render_response(monologue, route)
        return Response(
            text=text,
            monologue_id=monologue.id,
            route_type=route.route_type.value,
            confidence=monologue.confidence,
        )

    @staticmethod
    def _render_response(monologue: Monologue, route: Route) -> str:
        """Renderiza una respuesta textual mínima, honesta y útil.

        EIDOS NO finge ser un LLM cuando usa el stub. Declara su ruta
        abiertamente — esto es importante para debugging y confianza.
        """
        plan_str = "\n  - ".join(monologue.plan)
        route_str = route.route_type.value
        header = f"[EIDOS · backend={monologue.backend} · route={route_str} · conf={monologue.confidence:.2f}]"
        body = (
            f"\nObservación: {monologue.observation}\n"
            f"Hipótesis: {monologue.hypothesis}\n"
            f"Plan:\n  - {plan_str}\n"
            f"Riesgo: {monologue.risk}\n"
        )
        if route.next_action_hint:
            body += f"Próximo paso: {route.next_action_hint}\n"
        return header + body


__all__ = ["EidosCore", "Response"]
