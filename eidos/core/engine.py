"""EidosCore — orquestador principal del núcleo cognitivo. Fase 1.2.

Flujo (ampliado con memoria):
    user_input → SensoryMemory.store(user_input)
               → MonologueGenerator → Monologue
               → MetacognitiveMemory.store(monologue, route)
               → ActionRouter       → Route
               → EpisodicMemory.search() si route == SEARCH_MEMORY
               → (NLG/acción)       → Response
               → SensoryMemory.store(response)
               → EpisodicMemory.store(interaction)

La NLG real llega en Fase 2. La consolidación background en Fase 1.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.router import ActionRouter, Route
from eidos.memory.store import MemoryStore
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class Response(BaseModel):
    """Respuesta final de EIDOS al usuario."""

    text: str = Field(..., min_length=1)
    monologue_id: str
    route_type: str
    confidence: float
    # Fase 1.2: contexto recuperado de memoria (si route = SEARCH_MEMORY)
    memory_context: list[dict[str, Any]] | None = None


class EidosCore:
    """El núcleo cognitivo de EIDOS.

    Fase 1.1: orquestador pensar → decidir → responder.
    Fase 1.2: + memoria cognitiva de 5 capas integrada.
    """

    def __init__(
        self,
        monologue_backend: str = "stub",
        confidence_threshold: float = 0.6,
        monologues_dir: Path | None = None,
        max_plan_steps: int = 5,
        memory: MemoryStore | None = None,
    ) -> None:
        self._generator = MonologueGenerator(
            backend=monologue_backend,
            monologues_dir=monologues_dir,
            max_plan_steps=max_plan_steps,
        )
        self._router = ActionRouter(confidence_threshold=confidence_threshold)
        self._monologues_dir = monologues_dir
        self._memory = memory
        logger.info(
            "eidos_core_init",
            backend=monologue_backend,
            threshold=confidence_threshold,
            persist=bool(monologues_dir),
            memory=bool(memory),
        )

    def think_and_respond(self, user_input: str, context: str | None = None) -> Response:
        """Pipeline completo: input → memoria → monólogo → ruta → respuesta."""
        logger.debug("eidos_input", length=len(user_input))

        # 0. Sensory memory — registro del input
        if self._memory is not None:
            self._memory.sensory.store(
                kind="user_input",
                content=user_input,
                metadata={"context": context} if context else None,
            )

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

        # 3. Recuperar contexto de memoria si la ruta lo requiere
        memory_context: list[dict[str, Any]] | None = None
        if self._memory is not None and route.route_type.value == "search_memory":
            try:
                memory_context = self._memory.episodic.search(user_input, top_k=3)
                logger.info("eidos_memory_recall", hits=len(memory_context))
            except Exception as e:
                logger.warning("eidos_memory_recall_failed", error=str(e))

        # 4. Indexar monólogo en capa metacognitiva
        if self._memory is not None:
            try:
                self._memory.metacognitive.store(monologue, route_type=route.route_type.value)
            except Exception as e:
                logger.warning("eidos_metacognitive_store_failed", error=str(e))

        # 5. Responder (template; NLG real en Fase 2)
        text = self._render_response(monologue, route, memory_context)

        # 6. Sensory + Episodic memory — registro de la interacción
        if self._memory is not None:
            try:
                self._memory.sensory.store(
                    kind="response",
                    content=text[:200],  # truncar para sensory
                    metadata={"route": route.route_type.value, "monologue_id": monologue.id},
                )
                self._memory.episodic.store(
                    kind="interaction",
                    content=f"User: {user_input}\nEIDOS: {text[:200]}",
                    importance=monologue.confidence,
                    metadata={
                        "monologue_id": monologue.id,
                        "route": route.route_type.value,
                    },
                )
            except Exception as e:
                logger.warning("eidos_episodic_store_failed", error=str(e))

        return Response(
            text=text,
            monologue_id=monologue.id,
            route_type=route.route_type.value,
            confidence=monologue.confidence,
            memory_context=memory_context,
        )

    @staticmethod
    def _render_response(
        monologue: Monologue,
        route: Route,
        memory_context: list[dict[str, Any]] | None,
    ) -> str:
        """Renderiza una respuesta textual mínima, honesta y útil."""
        plan_str = "\n  - ".join(monologue.plan)
        route_str = route.route_type.value
        header = f"[EIDOS · backend={monologue.backend} · route={route_str} · conf={monologue.confidence:.2f}]"
        body = (
            f"\nObservación: {monologue.observation}\n"
            f"Hipótesis: {monologue.hypothesis}\n"
            f"Plan:\n  - {plan_str}\n"
            f"Riesgo: {monologue.risk}\n"
        )

        # Fase 1.2: incluir contexto recuperado de memoria
        if memory_context:
            body += "\nContexto recuperado de memoria episódica:\n"
            for i, ev in enumerate(memory_context, 1):
                content_preview = ev.get("content", "")[:120]
                score = ev.get("score", 0.0)
                body += f"  [{i}] (score={score:.2f}) {content_preview}\n"

        if route.next_action_hint:
            body += f"\nPróximo paso: {route.next_action_hint}\n"
        return header + body


__all__ = ["EidosCore", "Response"]
