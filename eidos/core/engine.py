"""EidosCore — orquestador principal del núcleo cognitivo. Fase 1.3.

Pipeline completo:
    user_input
      → MotivationModule.observe_user_input()     # reward de satisfacción
      → SensoryMemory.store(user_input)
      → MonologueGenerator → Monologue
      → MotivationModule.observe_confidence()     # reward de curiosidad
      → MetacognitiveMemory.store(monologue, route)
      → ActionRouter → Route
      → EpisodicMemory.search() si route == SEARCH_MEMORY
      → (NLG/acción) → Response
      → SensoryMemory.store(response)
      → EpisodicMemory.store(interaction)

Background:
    Consolidator (hilo daemon) cada 5 min:
      - compacta sensory → episódica
      - indexa monólogos huérfanos
      - infiere outcomes pendientes
      - expira cápsulas por TTL
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eidos.core.consolidator import Consolidator
from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.motivation import MotivationModule
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
    memory_context: list[dict[str, Any]] | None = None
    # Fase 1.3: reward signal del turno actual
    reward_delta: float = 0.0


class EidosCore:
    """El núcleo cognitivo de EIDOS."""

    def __init__(
        self,
        monologue_backend: str = "stub",
        confidence_threshold: float = 0.6,
        monologues_dir: Path | None = None,
        max_plan_steps: int = 5,
        memory: MemoryStore | None = None,
        motivation: MotivationModule | None = None,
        consolidator: Consolidator | None = None,
        auto_start_consolidator: bool = True,
    ) -> None:
        self._generator = MonologueGenerator(
            backend=monologue_backend,
            monologues_dir=monologues_dir,
            max_plan_steps=max_plan_steps,
        )
        self._router = ActionRouter(confidence_threshold=confidence_threshold)
        self._monologues_dir = monologues_dir
        self._memory = memory
        self._motivation = motivation
        self._consolidator = consolidator

        # Arrancar consolidador background si está configurado
        if self._consolidator is not None and auto_start_consolidator:
            self._consolidator.start()

        logger.info(
            "eidos_core_init",
            backend=monologue_backend,
            threshold=confidence_threshold,
            persist=bool(monologues_dir),
            memory=bool(memory),
            motivation=bool(motivation),
            consolidator=bool(consolidator),
        )

    def think_and_respond(self, user_input: str, context: str | None = None) -> Response:
        """Pipeline completo: input → memoria → monólogo → ruta → respuesta."""
        logger.debug("eidos_input", length=len(user_input))

        # 0a. Reward de satisfacción (heurística del input del usuario)
        reward_delta = 0.0
        if self._motivation is not None:
            try:
                reward_delta += self._motivation.observe_user_input(user_input)
            except Exception as e:
                logger.warning("motivation_observe_user_input_failed", error=str(e))

        # 0b. Sensory memory — registro del input
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

        # 1b. Reward de curiosidad (basado en confidence)
        if self._motivation is not None:
            try:
                reward_delta += self._motivation.observe_confidence(
                    monologue.confidence, monologue_id=monologue.id
                )
            except Exception as e:
                logger.warning("motivation_observe_confidence_failed", error=str(e))

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
                    content=text[:200],
                    metadata={
                        "route": route.route_type.value,
                        "monologue_id": monologue.id,
                        "confidence": monologue.confidence,
                    },
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
            reward_delta=round(reward_delta, 4),
        )

    def shutdown(self) -> None:
        """Detiene el consolidador background limpiamente."""
        if self._consolidator is not None:
            self._consolidator.stop()
            logger.info("eidos_core_shutdown_consolidator_stopped")

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
