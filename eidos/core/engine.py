"""EidosCore — orquestador principal del núcleo cognitivo. Fase 4.

Pipeline completo:
    user_input
      → MotivationModule.observe_user_input()     # reward de satisfacción
      → SensoryMemory.store(user_input)
      → MonologueGenerator → Monologue
          (Fase 2: stub | llama_cpp | api | auto vía CortexHub)
          (Fase 4: si soy Worker, el LLM se ejecuta en el Leader vía MESH)
      → MotivationModule.observe_confidence()     # reward de curiosidad
      → MetacognitiveMemory.store(monologue, route)
      → ActionRouter → Route
      → EpisodicMemory.search() si route == SEARCH_MEMORY
      → (NLG/acción) → Response
      → SensoryMemory.store(response)
      → EpisodicMemory.store(interaction)
      → EvolutionLoop.process_turn()  # Fase 3: detecta necesidad de cápsulas

Background:
    Consolidator (hilo daemon) cada 5 min
    Fase 4: MeshCoordinator (si mesh.enabled) — enjambre con leader election
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eidos.core.consolidator import Consolidator
from eidos.core.evolution import EvolutionLoop
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
    # Fase 2: backend usado para generar el monólogo
    monologue_backend: str = "stub"
    # Fase 3: si el turno disparó génesis de cápsula
    evolution_event: dict[str, Any] | None = None


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
        cortex_hub: Any = None,
        cortex_monologue_client: Any = None,
        evolution_loop: EvolutionLoop | None = None,
        mesh_coordinator: Any = None,
    ) -> None:
        """
        Args:
            monologue_backend: 'stub' | 'llama_cpp' | 'api' | 'auto'.
                'auto' (Fase 2): intenta CortexHub; si no hay modelo,
                degrada a stub.
            cortex_hub: instancia de CortexHub (Fase 2). Si es None y
                backend='auto', se usa stub.
            cortex_monologue_client: opcional, inyecta un LlamaClient en
                el backend del CortexHub (tests).
            evolution_loop: instancia de EvolutionLoop (Fase 3). Si es None,
                no se detectan necesidades de cápsulas automáticamente.
            mesh_coordinator: instancia de MeshCoordinator (Fase 4). Si es
                None, el nodo opera standalone (sin enjambre).
        """
        self._monologues_dir = monologues_dir
        self._memory = memory
        self._motivation = motivation
        self._consolidator = consolidator
        self._cortex_hub = cortex_hub
        self._cortex_client = cortex_monologue_client
        self._evolution_loop = evolution_loop
        self._mesh_coordinator = mesh_coordinator
        self._max_plan_steps = max_plan_steps
        # Fase 6: APIFallbackBackend inyectable en caliente
        self._api_backend: Any = None

        # Resolver backend real
        effective_backend, generator = self._resolve_backend(
            monologue_backend, monologues_dir, max_plan_steps
        )
        self._generator = generator
        self._effective_backend = effective_backend

        self._router = ActionRouter(confidence_threshold=confidence_threshold)

        # Arrancar consolidador background si está configurado
        if self._consolidator is not None and auto_start_consolidator:
            self._consolidator.start()

        logger.info(
            "eidos_core_init",
            backend=effective_backend,
            threshold=confidence_threshold,
            persist=bool(monologues_dir),
            memory=bool(memory),
            motivation=bool(motivation),
            consolidator=bool(consolidator),
            cortex=bool(cortex_hub),
            evolution=bool(evolution_loop),
            mesh=bool(mesh_coordinator),
        )

    def _resolve_backend(
        self,
        requested: str,
        monologues_dir: Path | None,
        max_plan_steps: int,
    ) -> tuple[str, MonologueGenerator]:
        """Resuelve qué backend usar de forma robusta.

        - 'stub' → siempre stub.
        - 'llama_cpp' → usa ese directo (debe estar instalado).
        - 'api' → requiere que se inyecte un APIFallbackBackend vía set_api_backend().
        - 'auto' → intenta CortexHub (llama_cpp si hay modelo), fallback a stub.
        """
        if requested == "auto":
            if self._cortex_hub is not None:
                try:
                    # Pedir lock antes de instanciar backend
                    if self._cortex_hub.try_acquire_lock(role="primary", ttl_sec=60.0):
                        backend = self._cortex_hub.get_monologue_backend(
                            max_plan_steps=max_plan_steps,
                            client=self._cortex_client,
                        )
                        if backend is not None:
                            self._cortex_backend = backend
                            gen = MonologueGenerator(
                                backend="llama_cpp",
                                monologues_dir=monologues_dir,
                                max_plan_steps=max_plan_steps,
                                backend_instance=backend,
                            )
                            return "llama_cpp", gen
                except Exception as e:
                    logger.warning("cortex_backend_resolution_failed", error=str(e))
            # Degradación a stub
            logger.info("cortex_auto_degraded_to_stub")
            return "stub", MonologueGenerator(
                backend="stub",
                monologues_dir=monologues_dir,
                max_plan_steps=max_plan_steps,
            )

        # Backend explícito
        if requested == "api":
            # Si ya hay un APIFallbackBackend inyectado, usarlo.
            # Si no, degradar a stub (no hay API key configurada todavía).
            if self._api_backend is not None:
                gen = MonologueGenerator(
                    backend="api",
                    monologues_dir=monologues_dir,
                    max_plan_steps=max_plan_steps,
                    backend_instance=self._api_backend,
                )
                return "api", gen
            logger.info("api_backend_not_configured_degraded_to_stub")
            return "stub", MonologueGenerator(
                backend="stub",
                monologues_dir=monologues_dir,
                max_plan_steps=max_plan_steps,
            )

        gen = MonologueGenerator(
            backend=requested,
            monologues_dir=monologues_dir,
            max_plan_steps=max_plan_steps,
        )
        return requested, gen

    def set_api_backend(self, backend: Any) -> None:
        """Inyecta un APIFallbackBackend y activa el backend 'api' en caliente.

        Fase 6: permite a la UI cambiar de provider (OpenAI, Anthropic,
        MiniMax-M3 vía Anthropic, etc.) sin reiniciar el servidor.

        Args:
            backend: instancia de APIFallbackBackend ya configurada.
        """
        self._api_backend = backend
        # Reconstruir el generador con el nuevo backend
        self._generator = MonologueGenerator(
            backend="api",
            monologues_dir=self._monologues_dir,
            max_plan_steps=self._max_plan_steps,
            backend_instance=backend,
        )
        self._effective_backend = "api"
        logger.info(
            "eidos_api_backend_set",
            api_type=getattr(backend, "_api_type", "openai"),
            model=getattr(backend, "_model", "?"),
        )

    @property
    def api_backend(self) -> Any:
        """Devuelve el APIFallbackBackend activo, o None."""
        return getattr(self, "_api_backend", None)

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

        # 7. Fase 3: EvolutionLoop — detecta necesidad de cápsulas
        evolution_event: dict[str, Any] | None = None
        if self._evolution_loop is not None:
            try:
                evolution_event = self._evolution_loop.process_turn(user_input, monologue)
                if evolution_event is not None:
                    logger.info(
                        "eidos_evolution_triggered",
                        topic=evolution_event.get("topic"),
                        decision=evolution_event.get("decision"),
                    )
            except Exception as e:
                logger.warning("eidos_evolution_failed", error=str(e))

        return Response(
            text=text,
            monologue_id=monologue.id,
            route_type=route.route_type.value,
            confidence=monologue.confidence,
            memory_context=memory_context,
            reward_delta=round(reward_delta, 4),
            monologue_backend=monologue.backend,
            evolution_event=evolution_event,
        )

    @property
    def mesh(self) -> Any:
        """Acceso al MeshCoordinator (None si no está activo)."""
        return self._mesh_coordinator

    def shutdown(self) -> None:
        """Detiene consolidador, libera CortexHub y detiene MeshCoordinator."""
        if self._consolidator is not None:
            self._consolidator.stop()
            logger.info("eidos_core_shutdown_consolidator_stopped")
        if self._cortex_hub is not None:
            try:
                self._cortex_hub.close()
                logger.info("eidos_core_shutdown_cortex_closed")
            except Exception as e:
                logger.warning("eidos_core_shutdown_cortex_failed", error=str(e))
        if self._mesh_coordinator is not None:
            try:
                self._mesh_coordinator.stop()
                logger.info("eidos_core_shutdown_mesh_stopped")
            except Exception as e:
                logger.warning("eidos_core_shutdown_mesh_failed", error=str(e))

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
