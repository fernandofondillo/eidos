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

        # AUTO-RESTAURAR provider activo desde .env al arrancar.
        # Si el usuario configuró MiniMax/OpenAI/etc. en una sesión anterior,
        # EIDOS lo restaura automáticamente al reiniciar.
        self._try_restore_api_backend()

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
        """Pipeline cognitivo de EIDOS.

        EIDOS es el que PIENSA. El LLM es un SENTIDO que articula.

        Flujo:
        0. EIDOS registra el input en memoria sensorial.
        1. EIDOS RAZONA por sí mismo: ¿puedo responder sin el LLM?
           → Si puede: responde directo (backend=eidos_direct, sin LLM).
           → Si no puede: construye contexto y usa el LLM.
        2. EIDOS construye el CONTEXTO COGNITIVO (historial + hechos + cápsula).
        3. EIDOS le pide al LLM que genere el monólogo + respuesta.
        4. EIDOS decide la ruta, registra en memoria, actualiza semántica.
        """
        logger.debug("eidos_input", length=len(user_input))

        # 0a. Reward de satisfacción (solo positiva)
        reward_delta = 0.0
        if self._motivation is not None:
            try:
                reward_delta += self._motivation.observe_user_input("(neutral input)")
            except Exception as e:
                logger.warning("motivation_observe_user_input_failed", error=str(e))

        # 0b. Sensory memory — registro del input
        if self._memory is not None:
            self._memory.sensory.store(
                kind="user_input",
                content=user_input,
                metadata={"context": context} if context else None,
            )

        # ================================================================
        # 1. EIDOS DIRECT RESPONSE — EIDOS razona SIN el LLM
        # ================================================================
        # EIDOS puede responder preguntas simples directamente desde su
        # memoria, SIN llamar al LLM. Esto demuestra que EIDOS piensa
        # por sí mismo — el LLM es solo un sentido para tareas complejas.
        direct_response = self._try_direct_response(user_input)
        if direct_response is not None:
            # EIDOS respondió por sí mismo. No necesita el LLM.
            logger.info("eidos_direct_response", question_type=direct_response.get("type", "unknown"))

            # Construir Monologue sintético (EIDOS lo genera, no el LLM)
            import uuid
            from datetime import datetime, timezone
            monologue = Monologue(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                input_summary=user_input[:500],
                observation=f"EIDOS respondió directamente desde memoria: {direct_response['type']}",
                hypothesis=f"Pregunta simple sobre {direct_response['type']}, respondible sin LLM.",
                plan=["Responder desde memoria semántica", "No requiere LLM"],
                risk="none",
                confidence=0.99,
                response=direct_response["text"],
                backend="eidos_direct",
            )

            # Reward de curiosidad alta (EIDOS está seguro)
            if self._motivation is not None:
                try:
                    reward_delta += self._motivation.observe_confidence(0.99, monologue_id=monologue.id)
                except Exception:
                    pass

            route = self._router.decide(monologue)
            text = direct_response["text"]

            # Registrar en memoria
            if self._memory is not None:
                try:
                    self._memory.sensory.store(
                        kind="response", content=text[:200],
                        metadata={"route": "respond_direct", "monologue_id": monologue.id, "confidence": 0.99},
                    )
                    self._memory.episodic.store(
                        kind="interaction", content=f"User: {user_input}\nEIDOS: {text[:200]}",
                        importance=0.99, metadata={"monologue_id": monologue.id, "route": "respond_direct", "backend": "eidos_direct"},
                    )
                    self._memory.metacognitive.store(monologue, route_type="respond_direct")
                    self._extract_facts_and_update_semantic(user_input, text)
                    self._mark_relevant_capsules_used(user_input)
                except Exception as e:
                    logger.warning("eidos_direct_memory_store_failed", error=str(e))

            return Response(
                text=f"[EIDOS · backend=eidos_direct · route=respond_direct · conf=0.99]\n{text}",
                monologue_id=monologue.id,
                route_type="respond_direct",
                confidence=0.99,
                reward_delta=round(reward_delta, 4),
                monologue_backend="eidos_direct",
            )

        # ================================================================
        # 2. CONTEXT ENGINE — EIDOS construye el contexto para el LLM
        # ================================================================
        # EIDOS no pudo responder solo. Necesita el LLM (su sentido).
        # Le construye un contexto cognitivo completo.

        full_context = context or ""

        if self._memory is not None:
            # a) HISTORIAL CONVERSACIONAL de esta sesión
            recent_events = self._memory.sensory.recent(limit=10)
            conversation_history: list[str] = []
            for ev in reversed(recent_events):
                kind = ev.get("kind", "")
                content = ev.get("content", "")
                if kind == "user_input" and content:
                    conversation_history.append(f"Usuario: {content}")
                elif kind == "response" and content:
                    conversation_history.append(f"EIDOS: {content}")
            if len(conversation_history) > 10:
                conversation_history = conversation_history[-10:]
            if conversation_history:
                history_str = "\n".join(conversation_history)
                full_context = (full_context + "\n" if full_context else "") + f"Historial de nuestra conversación actual:\n{history_str}"

            # b) HECHOS SEMÁNTICOS confirmados
            sem_ctx = self._query_semantic_for_context(user_input)
            if sem_ctx:
                full_context = (full_context + "\n" if full_context else "") + sem_ctx

            # c) CÁPSULA ACTIVA relevante
            active_capsules = self._memory.procedural.list_all(include_expired=False)
            relevant_capsules: list[str] = []
            for cap in active_capsules:
                name_lower = cap.name.lower()
                topic = name_lower
                for prefix in ("experto en ", "experta en ", "experto ", "experta "):
                    if topic.startswith(prefix):
                        topic = topic[len(prefix):]
                        break
                topic = topic.strip()
                if topic and len(topic) >= 3:
                    topic_words = [w for w in topic.split() if len(w) >= 3]
                    input_lower = user_input.lower()
                    if any(w in input_lower for w in topic_words) or topic in input_lower:
                        relevant_capsules.append(cap.name)
            if relevant_capsules:
                caps_str = ", ".join(relevant_capsules)
                full_context = (full_context + "\n" if full_context else "") + f"Especialidad activa: {caps_str}"

            # d) RESUMEN DE SESIONES ANTERIORES (cross-session memory)
            session_summary = self._load_session_summary()
            if session_summary:
                full_context = (full_context + "\n" if full_context else "") + f"Resumen de sesiones anteriores:\n{session_summary}"

        # 3. EIDOS usa el LLM (su sentido) para generar el monólogo + respuesta
        monologue = self._generator.generate(user_input, full_context if full_context else None)
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

        # 5. Responder
        # El LLM ya recibió el contexto completo (historial + hechos + cápsula)
        # en el paso 1, así que su respuesta YA usa la memoria.
        # Ya NO añadimos '💡' después — el LLM debe saberlo antes de responder.
        text = self._render_response(monologue, route, memory_context)

        # 6. Sensory + Episodic + Semantic memory — registro de la interacción
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
                # NUEVO (Fase 6.1): Extraer hechos del input + respuesta y
                # poblar el grafo semántico. Sin esto, EIDOS no recuerda nada.
                self._extract_facts_and_update_semantic(user_input, text)

                # NUEVO (Fase 6.1): Marcar cápsulas relevantes como usadas.
                # Si el input del usuario contiene el nombre de una cápsula
                # activa, incrementar su contador de uso.
                self._mark_relevant_capsules_used(user_input)
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

        # ================================================================
        # 8. TOOL CREATION — EIDOS crea herramientas autónomamente
        # ================================================================
        # Si el usuario pide una herramienta ("crea una tool que X"),
        # EIDOS extrae el código de la respuesta del LLM, lo valida en
        # el ToolSandbox, y si pasa, lo guarda como tool reutilizable.
        tool_event: dict[str, Any] | None = None
        tool_event = self._try_tool_creation(user_input, monologue, text)

        # ================================================================
        # 9. AUTO-EVOLUTION — EIDOS evoluciona su comportamiento
        # ================================================================
        # a) Promover cápsulas con uses >= 3 a favoritas.
        # b) Detectar patrón de corrección: si el usuario ha dicho algo
        #    negativo recientemente, ajustar confianza.
        auto_evolution_event: dict[str, Any] | None = None
        auto_evolution_event = self._run_auto_evolution(user_input, monologue)

        # Combinar evolution_event con tool_event y auto_evolution_event
        combined_evolution = evolution_event
        if tool_event:
            combined_evolution = combined_evolution or {}
            combined_evolution["tool_created"] = tool_event
        if auto_evolution_event:
            combined_evolution = combined_evolution or {}
            combined_evolution["auto_evolution"] = auto_evolution_event

        return Response(
            text=text,
            monologue_id=monologue.id,
            route_type=route.route_type.value,
            confidence=monologue.confidence,
            memory_context=memory_context,
            reward_delta=round(reward_delta, 4),
            monologue_backend=monologue.backend,
            evolution_event=combined_evolution,
        )

    @property
    def mesh(self) -> Any:
        """Acceso al MeshCoordinator (None si no está activo)."""
        return self._mesh_coordinator

    def shutdown(self) -> None:
        """Detiene consolidador, libera CortexHub, detiene Mesh, guarda sesión."""
        # Guardar resumen de sesión para cross-session memory
        self._save_session_summary()
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

    def _try_restore_api_backend(self) -> None:
        """Restaura el provider API activo desde .env al arrancar.

        Lee data/active_provider.json (si existe) para saber qué provider
        estaba activo la última vez. Lee las keys de .env y reconstruye
        el APIFallbackBackend correspondiente.
        """
        import json
        import os

        try:
            # 1. Leer qué provider estaba activo
            if self._monologues_dir is None:
                return
            active_path = self._monologues_dir.parent / "active_provider.json"
            if not active_path.exists():
                return

            active_data = json.loads(active_path.read_text(encoding="utf-8"))
            provider_id = active_data.get("provider_id")
            if not provider_id:
                return

            # 2. Buscar el provider en el catálogo
            try:
                from eidos.web.providers import get_provider
            except ImportError:
                return  # providers.py solo disponible cuando el web server está activo

            provider = get_provider(provider_id)
            if provider is None:
                return

            # 3. Leer la API key desde .env
            env_path = self._monologues_dir.parent.parent / ".env"
            api_key = ""
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith(f"{provider.env_var}="):
                        api_key = line.split("=", 1)[1].strip()
                        break

            if not api_key:
                return  # No hay key configurada

            # 4. Reconstruir el backend
            os.environ[provider.env_var] = api_key
            from eidos.cortex.api_fallback import APIFallbackBackend

            backend = APIFallbackBackend(
                base_url=provider.base_url,
                api_key_env=provider.env_var,
                model=provider.default_model,
                api_type=provider.api_type,
            )
            self.set_api_backend(backend)
            logger.info("eidos_api_backend_restored", provider=provider_id, model=provider.default_model)

        except Exception as e:
            logger.warning("eidos_api_backend_restore_failed", error=str(e))

    def _try_tool_creation(self, user_input: str, monologue: Monologue, response_text: str) -> dict[str, Any] | None:
        """EIDOS crea herramientas autónomamente.

        Si el usuario pide una herramienta ("crea una tool que X", "hazme
        una función que Y"), EIDOS:
        1. Extrae código Python de la respuesta del LLM.
        2. Lo valida en el ToolSandbox (AST + ejecución segura).
        3. Si pasa, lo guarda como tool reutilizable en la cápsula activa
           o crea una nueva cápsula para alojarlo.
        4. Si no pasa, informa al usuario del error.

        Returns:
            dict con 'created', 'name', 'status' o None si no aplica.
        """
        import re

        input_lower = user_input.lower()

        # Detectar si el usuario pide una herramienta o aprueba una propuesta
        tool_triggers = [
            "crea una tool", "crea una herramienta", "crea una función",
            "hazme una función", "hazme una tool", "crea un script",
            "escribe una función", "programa una función", "crea código que",
            "crea una herramienta que", "vamos a por ella", "intégrala",
            "intégala", "hazlo", "regístrala", "aprueba", "procede",
            "adelante", "sí, hazlo", "si hazlo", "vamos alla", "vamos a la",
        ]
        if not any(t in input_lower for t in tool_triggers):
            return None

        logger.info("eidos_tool_creation_detected", input=user_input[:100])

        # Extraer código Python de la respuesta del LLM
        # Buscar bloques ```python ... ``` o ``` ... ```
        code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', response_text, re.DOTALL)
        if not code_blocks:
            # Buscar funciones def ... que no estén en markdown
            code_blocks = re.findall(r'((?:def\s+\w+\s*\([^)]*\)\s*:\s*\n(?:\s+.*\n?)+)+)', response_text)
        if not code_blocks:
            return {"created": False, "reason": "No se encontró código Python en la respuesta."}

        code = code_blocks[0].strip()

        # Extraer nombre de la función principal
        func_match = re.search(r'def\s+(\w+)\s*\(', code)
        if not func_match:
            return {"created": False, "reason": "No se encontró función 'def' en el código."}
        tool_name = func_match.group(1)

        # Validar en ToolSandbox
        try:
            from eidos.core.sandbox import ToolSandbox
            sandbox = ToolSandbox(timeout_sec=5, mem_limit_mb=128)
            result = sandbox.run_code(code, entry=None)  # solo cargar, no ejecutar

            if result.is_security_error:
                logger.warning("eidos_tool_security_rejected", tool=tool_name, violations=result.security_violations)
                return {
                    "created": False,
                    "name": tool_name,
                    "status": "rejected_security",
                    "reason": f"El código fue rechazado por seguridad: {result.security_violations}",
                }

            # Hacer smoke test: ejecutar la función sin args (si acepta defaults)
            smoke_result = sandbox.smoke_test_tool(code, entry=tool_name, test_args={})
            if not smoke_result.ok and smoke_result.exit_code != 2:  # exit 2 = "entry not found" (OK si tiene args)
                logger.warning("eidos_tool_smoke_failed", tool=tool_name, error=smoke_result.stderr[:200])
                return {
                    "created": False,
                    "name": tool_name,
                    "status": "smoke_test_failed",
                    "reason": f"La herramienta falló al ejecutarse: {smoke_result.stderr[:200]}",
                }

            # Si pasa, guardar como tool
            if self._memory is not None:
                # Buscar cápsula activa relevante o crear una nueva
                from eidos.core.forge import CapsuleForge, StubForgeBackend
                from eidos.core.sandbox import ToolSandbox as TS

                forge = CapsuleForge(
                    db_path=self._memory.db_path,
                    procedural=self._memory.procedural,
                    backend=StubForgeBackend(),
                    sandbox=TS(),
                )

                # Crear cápsula con la tool
                from eidos.core.forge import CapsuleDraft, CapsuleOntology, CapsuleRule, CapsuleTone, CapsuleTool
                draft = CapsuleDraft(
                    name=f"Herramienta: {tool_name}",
                    version="1.0.0",
                    description=f"Herramienta '{tool_name}' creada por EIDOS a petición del usuario.",
                    ontology=CapsuleOntology(domain="tools"),
                    rules=[
                        CapsuleRule(
                            id="r1",
                            condition=f"Usuario necesita usar {tool_name}",
                            action=f"Ejecutar {tool_name} desde la tool guardada",
                            priority=1,
                        )
                    ],
                    tone=CapsuleTone(style="technical"),
                    tools=[
                        CapsuleTool(
                            name=tool_name,
                            entry_point=tool_name,
                            code=code,
                        )
                    ],
                    genesis_confidence=0.9,
                    smoke_test_passed=True,
                    smoke_test_output=f"Tool {tool_name} validada en sandbox.",
                )

                # Forzar pending (las tools requieren aprobación humana por seguridad)
                forge._persist_draft(draft, __import__("eidos.core.forge", fromlist=["ForgeDecision"]).ForgeDecision.PENDING_APPROVAL)

                logger.info("eidos_tool_created", tool=tool_name, status="pending_approval")
                return {
                    "created": True,
                    "name": tool_name,
                    "status": "pending_approval",
                    "message": f"He creado la herramienta '{tool_name}', la he validado en el sandbox, y está lista para usar. Apruébala en el panel de Cápsulas.",
                }

        except Exception as e:
            logger.error("eidos_tool_creation_error", error=str(e))
            return {"created": False, "reason": f"Error al crear la tool: {e}"}

        return None

    def _run_auto_evolution(self, user_input: str, monologue: Monologue) -> dict[str, Any] | None:
        """EIDOS evoluciona su comportamiento basándose en la experiencia.

        a) PROMOCIÓN: si una cápsula tiene uses >= 3, la promueve a favorita.
        b) DETECCIÓN DE PATRÓN: si el usuario pide lo mismo 3+ veces,
           EIDOS crea una cápsula automáticamente.
        c) AJUSTE DE CONFIANZA: si el reward acumulado es negativo,
           EIDOS baja su confidence_threshold temporalmente.

        Returns:
            dict con eventos de evolución, o None.
        """
        events: list[str] = []

        if self._memory is None:
            return None

        try:
            # a) PROMOVER cápsulas con uses >= 3 a favoritas
            if self._evolution_loop is not None:
                try:
                    promoted = self._evolution_loop.check_promotions()
                    if promoted:
                        events.append(f"Cápsulas promovidas a favoritas: {', '.join(promoted)}")
                        logger.info("auto_evolution_promoted", count=len(promoted))
                except Exception as e:
                    logger.warning("auto_evolution_promote_failed", error=str(e))

            # b) DETECTAR PATRÓN RECURRENTE
            # Si el usuario ha preguntado por el mismo tema 3+ veces en
            # los últimos eventos sensoriales, y no hay cápsula para eso,
            # crear una automáticamente.
            try:
                recent = self._memory.sensory.recent(limit=20)
                user_inputs = [ev.get("content", "").lower() for ev in recent if ev.get("kind") == "user_input"]

                if len(user_inputs) >= 3:
                    # Buscar palabra que aparezca en 3+ inputs
                    from collections import Counter
                    word_counts: Counter[str] = Counter()
                    for inp in user_inputs:
                        words = [w for w in inp.split() if len(w) >= 4]
                        word_counts.update(words)

                    for word, count in word_counts.most_common(5):
                        if count >= 3:
                            # Verificar si ya existe una cápsula para este tema
                            existing_caps = self._memory.procedural.list_all()
                            already_exists = any(
                                word in c.name.lower() for c in existing_caps
                            )
                            if not already_exists:
                                # Crear cápsula automáticamente
                                from eidos.core.forge import CapsuleForge, StubForgeBackend
                                forge = CapsuleForge(
                                    db_path=self._memory.db_path,
                                    procedural=self._memory.procedural,
                                    backend=StubForgeBackend(),
                                )
                                draft, decision = forge.forge(
                                    f"experto en {word}",
                                    context={"requested_by": "auto_evolution_pattern"},
                                )
                                if decision.value == "auto_approved":
                                    events.append(f"Cápsula auto-creada por patrón recurrente: Experto en {word}")
                                    logger.info("auto_evolution_pattern_capsule", word=word, count=count)
                                break  # solo 1 por turno
            except Exception as e:
                logger.warning("auto_evolution_pattern_failed", error=str(e))

            # c) AJUSTE DE CONFIANZA basado en reward acumulado
            if self._motivation is not None:
                try:
                    total_reward = self._motivation.total_reward()
                    current_threshold = self._router.confidence_threshold

                    if total_reward < -1.0 and current_threshold > 0.4:
                        # Bajar threshold: ser más cauteloso, pedir más aclaraciones
                        self._router = type(self._router)(confidence_threshold=0.4)
                        events.append("Ajuste: bajando threshold de confianza (reward negativo acumulado)")
                        logger.info("auto_evolution_threshold_lowered", total_reward=total_reward)
                    elif total_reward > 2.0 and current_threshold < 0.7:
                        # Subir threshold: ser más seguro, responder directo
                        self._router = type(self._router)(confidence_threshold=0.7)
                        events.append("Ajuste: subiendo threshold de confianza (reward positivo)")
                        logger.info("auto_evolution_threshold_raised", total_reward=total_reward)
                except Exception as e:
                    logger.warning("auto_evolution_confidence_failed", error=str(e))

        except Exception as e:
            logger.warning("auto_evolution_failed", error=str(e))

        if events:
            return {"events": events}
        return None

    def _try_direct_response(self, user_input: str) -> dict[str, Any] | None:
        """EIDOS razona por sí mismo: ¿puede responder sin el LLM?

        Si el usuario pregunta por algo que EIDOS sabe (nombre, profesión,
        preferencias, edad, ciudad), EIDOS responde directamente desde su
        grafo semántico — SIN llamar al LLM.

        Returns:
            dict con 'text' y 'type', o None si EIDOS no puede responder solo.
        """
        if self._memory is None:
            return None

        try:
            sem = self._memory.semantic
            user_entity = sem.get_entity("usuario")
            if user_entity is None:
                return None  # No hay datos del usuario todavía

            input_lower = user_input.lower()
            all_rels = sem.query_relations("usuario", direction="out")

            # ¿Pregunta por su nombre?
            name_triggers = ["cómo me llamo", "mi nombre", "quién soy", "cómo te llamas",
                             "recuerdas mi nombre", "quién soy yo", "me llamo"]
            if any(p in input_lower for p in name_triggers):
                name_rels = [r for r in all_rels if r.get("predicate") == "tiene_nombre"]
                if name_rels:
                    name_val = name_rels[-1].get("dst", "").replace("_", " ").title()
                    return {"text": f"Te llamas {name_val}.", "type": "nombre"}

            # ¿Pregunta por su profesión?
            prof_triggers = ["a qué me dedico", "mi trabajo", "mi profesión", "qué hago", "a qué te dedicas"]
            if any(p in input_lower for p in prof_triggers):
                prof_rels = [r for r in all_rels if r.get("predicate") == "tiene_profesion"]
                if prof_rels:
                    prof_val = prof_rels[-1].get("dst", "")
                    return {"text": f"Te dedicas a {prof_val}.", "type": "profesion"}

            # ¿Pregunta por sus preferencias?
            pref_triggers = ["qué me gusta", "mis gustos", "mis preferencias"]
            if any(p in input_lower for p in pref_triggers):
                prefs = []
                for r in all_rels:
                    if r.get("predicate") in ("le_gusta", "prefiere", "odia", "le_apasiona"):
                        pred_map = {"le_gusta": "Te gusta", "prefiere": "Prefieres", "odia": "Odias", "le_apasiona": "Te apasiona"}
                        prefs.append(f"{pred_map.get(r['predicate'], r['predicate'])} {r.get('dst', '')}")
                if prefs:
                    return {"text": "; ".join(prefs) + ".", "type": "preferencias"}

            # ¿Pregunta por su edad?
            age_triggers = ["cuántos años", "mi edad"]
            if any(p in input_lower for p in age_triggers):
                for r in all_rels:
                    if r.get("predicate") == "tiene_edad":
                        age = r.get("dst", "").replace("_años", "")
                        return {"text": f"Tienes {age} años.", "type": "edad"}

            # ¿Pregunta por dónde vive?
            city_triggers = ["dónde vivo", "dónde nací", "de dónde soy"]
            if any(p in input_lower for p in city_triggers):
                for r in all_rels:
                    if r.get("predicate") == "vive_en":
                        city = r.get("dst", "").title()
                        return {"text": f"Vives en {city}.", "type": "ciudad"}

            # ¿Pregunta "qué sabes de mí"?
            if any(p in input_lower for p in ["qué sabes de mí", "qué recuerdas de mí", "qué sabes de mi"]):
                facts = []
                for r in all_rels:
                    if r.get("predicate") == "tiene_nombre":
                        facts.append(f"Te llamas {r.get('dst', '').replace('_', ' ').title()}")
                    elif r.get("predicate") == "tiene_profesion":
                        facts.append(f"Te dedicas a {r.get('dst', '')}")
                    elif r.get("predicate") == "vive_en":
                        facts.append(f"Vives en {r.get('dst', '').title()}")
                    elif r.get("predicate") == "tiene_edad":
                        facts.append(f"Tienes {r.get('dst', '').replace('_años', '')} años")
                    elif r.get("predicate") == "tiene_proyecto":
                        facts.append(f"Tienes un proyecto: {r.get('dst', '')}")
                if facts:
                    return {"text": "Esto es lo que sé de ti: " + "; ".join(facts) + ".", "type": "perfil_completo"}

            # ¿Pregunta por sus proyectos?
            if any(p in input_lower for p in ["mi proyecto", "qué proyecto", "qué estoy trabajando", "retoma el plan", "retoma el proyecto"]):
                proj_rels = [r for r in all_rels if r.get("predicate") == "tiene_proyecto"]
                if proj_rels:
                    projects = [r.get("dst", "") for r in proj_rels]
                    return {"text": f"Tu proyecto activo es: {', '.join(projects)}.", "type": "proyecto"}

            # ¿Pregunta por sus cápsulas?
            if any(p in input_lower for p in ["qué cápsulas", "qué especialidades", "tienes cápsulas"]):
                caps = self._memory.procedural.list_all(include_expired=False)
                if caps:
                    cap_names = [c.name for c in caps]
                    return {"text": f"Tengo {len(caps)} cápsula(s) activa(s): {', '.join(cap_names)}.", "type": "cápsulas"}

            # No puede responder directamente → necesita el LLM
            return None

        except Exception as e:
            logger.warning("eidos_direct_response_failed", error=str(e))
            return None

    def _load_session_summary(self) -> str | None:
        """Carga un resumen de sesiones anteriores para cross-session memory.

        Lee data/session_summary.json (si existe) y devuelve un string
        con los puntos clave de conversaciones pasadas.
        """
        if self._monologues_dir is None:
            return None
        summary_path = self._monologues_dir.parent / "session_summary.json"
        if not summary_path.exists():
            return None
        try:
            import json
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "summary" in data:
                return data["summary"]
            if isinstance(data, str):
                return data
        except Exception:
            pass
        return None

    def _save_session_summary(self) -> None:
        """Guarda un resumen de la sesión actual para cross-session memory.

        Extrae los hechos semánticos y los últimos temas tratados, y los
        guarda en data/session_summary.json.
        """
        if self._memory is None or self._monologues_dir is None:
            return
        try:
            import json
            sem = self._memory.semantic
            all_rels = sem.query_relations("usuario", direction="out")

            facts: list[str] = []
            for r in all_rels:
                pred = r.get("predicate", "")
                dst = r.get("dst", "")
                if pred == "tiene_nombre":
                    facts.append(f"El usuario se llama {dst.replace('_', ' ').title()}")
                elif pred == "tiene_profesion":
                    facts.append(f"Se dedica a {dst}")
                elif pred == "vive_en":
                    facts.append(f"Vive en {dst.title()}")
                elif pred == "tiene_edad":
                    facts.append(f"Tiene {dst.replace('_años', '')} años")
                elif pred == "le_gusta":
                    facts.append(f"Le gusta {dst}")
                elif pred == "le_apasiona":
                    facts.append(f"Le apasiona {dst}")

            # Cápsulas activas
            caps = self._memory.procedural.list_all(include_expired=False)
            if caps:
                cap_names = [c.name for c in caps]
                facts.append(f"Cápsulas activas: {', '.join(cap_names)}")

            summary = {
                "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "summary": ". ".join(facts) if facts else "Sesión sin hechos específicos registrados.",
            }

            summary_path = self._monologues_dir.parent / "session_summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("session_summary_saved", path=str(summary_path), facts=len(facts))
        except Exception as e:
            logger.warning("session_summary_save_failed", error=str(e))

    def _mark_relevant_capsules_used(self, user_input: str) -> None:
        """Si el input del usuario menciona el tema de una cápsula activa,
        marca esa cápsula como usada (incrementa uses + actualiza last_used).
        """
        if self._memory is None:
            return
        try:
            input_lower = user_input.lower()
            active_capsules = self._memory.procedural.list_all(include_expired=False)
            for cap in active_capsules:
                # Extraer palabras clave del nombre de la cápsula
                # ej: "Experto en Marketing" → "marketing"
                name_lower = cap.name.lower()
                # Quitar prefijos comunes
                topic = name_lower
                for prefix in ("experto en ", "experta en ", "experto ", "experta "):
                    if topic.startswith(prefix):
                        topic = topic[len(prefix):]
                        break
                topic = topic.strip()

                # Matching flexible: si alguna palabra del topic (>=3 chars)
                # aparece en el input del usuario, contar como uso.
                topic_words = [w for w in topic.split() if len(w) >= 3]
                matched = False
                for word in topic_words:
                    if word in input_lower:
                        matched = True
                        break

                # También matching por tema completo si es una sola palabra
                if not matched and topic and len(topic) >= 3 and topic in input_lower:
                    matched = True

                if matched:
                    self._memory.procedural.mark_used(cap.id)
                    # Reward de reutilización de cápsula
                    if self._motivation is not None:
                        try:
                            self._motivation.reward_capsule_use(cap.id)
                        except Exception:
                            pass
                    logger.info("capsule_marked_used", id=cap.id, name=cap.name)
        except Exception as e:
            logger.warning("capsule_mark_used_failed", error=str(e))

    def _extract_facts_and_update_semantic(self, user_input: str, response: str) -> None:
        """Extrae hechos del INPUT DEL USUARIO (no de la respuesta del LLM)
        y los guarda en el grafo semántico.

        IMPORTANTE: Solo extraemos del user_input. La respuesta del LLM
        puede decir "soy EIDOS" o "soy bastante curioso" y NO queremos
        capturar eso como un nombre del usuario.
        """
        import re

        if self._memory is None:
            return
        try:
            sem = self._memory.semantic

            # === SOLO extraer del INPUT del usuario ===
            # NO combinar con la respuesta del LLM (causaba contaminación).

            # Patrón 1: "Me llamo X" / "Mi nombre es X"
            # Patrón ESTRICTO: solo estos dos patrones, no "soy X" (que captura basura).
            name_patterns = [
                r"\b(?:me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)",
            ]
            for pat in name_patterns:
                m = re.search(pat, user_input, re.IGNORECASE)
                if m:
                    name = m.group(1).strip().rstrip(".,;")
                    # Capitalizar primera letra
                    name = name[0].upper() + name[1:] if name else name
                    # Filtrar palabras que claramente no son nombres
                    not_names = {
                        "yo", "tu", "el", "ella", "eso", "este", "aqui",
                        "ahora", "hoy", "ayer", "luego", "despues",
                        "bastante", "curioso", "quien", "entonces",
                        "mismo", "muy", "poco", "mucho", "todo", "nada",
                        "eidos", "ia", "ai", "bot", "chatbot",
                    }
                    if name and len(name) >= 2 and name.lower() not in not_names:
                        # Si ya existe un nombre distinto, REEMPLAZARLO (no acumular).
                        existing_rels = sem.query_relations("usuario", direction="out")
                        for r in existing_rels:
                            if r.get("predicate") == "tiene_nombre" and r.get("dst") != name.lower().replace(" ", "_"):
                                # Borrar el nombre anterior del grafo
                                try:
                                    sem._graph.remove_edge("usuario", r["dst"])
                                    logger.info("semantic_name_replaced", old=r["dst"], new=name.lower().replace(" ", "_"))
                                except Exception:
                                    pass
                        sem.add_entity("usuario", "person", {"name": name})
                        sem.add_relation("usuario", "tiene_nombre", name.lower().replace(" ", "_"))
                        logger.info("semantic_fact_extracted", type="name", value=name)
                        break

            # Patrón 2: "Soy [profesión]" — solo del user_input
            # Usar SOLO patrones explícitos de profesión, no "soy X" genérico.
            prof_patterns = [
                r"\btrabajo como\s+(\w+(?:\s+\w+)?)",
                r"\bme dedico a\s+(?:la\s+|el\s+)?(\w+(?:\s+\w+)?)",
                r"\bsoy\s+(desarrollador|programador|ingeniero|abogado|médico|doctor|profesor|maestro|diseñador|arquitecto|consultor|analista|gerente|director|empresario|periodista|escritor|artista|músico|fotógrafo|coach|entrenador|investigador|científico|contador|economista)(?:\s+de\s|,|$)",
            ]
            for pat in prof_patterns:
                m = re.search(pat, user_input, re.IGNORECASE)
                if m:
                    prof = m.group(1).strip().rstrip(".,;").lower()
                    if prof and len(prof) >= 3:
                        sem.add_entity("usuario", "person", {"profession": prof})
                        sem.add_relation("usuario", "tiene_profesion", prof)
                        logger.info("semantic_fact_extracted", type="profession", value=prof)
                        break

            # Patrón 3: "Me gusta X" / "Prefiero X" / "Odio X" / "Me apasiona X"
            pref_patterns = [
                (r"\bme gusta\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "le_gusta"),
                (r"\bprefiero\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "prefiere"),
                (r"\bodio\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "odia"),
                (r"\bme apasiona\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "le_apasiona"),
            ]
            for pat, pred in pref_patterns:
                m = re.search(pat, user_input, re.IGNORECASE)
                if m:
                    obj = m.group(1).strip().rstrip(".,;").lower()
                    if obj and len(obj) >= 2 and obj not in {"yo", "tu", "el", "ella", "eso", "este"}:
                        sem.add_entity(obj, "concept")
                        sem.add_relation("usuario", pred, obj)
                        logger.info("semantic_fact_extracted", type="preference", predicate=pred, value=obj)
                        break

            # Patrón 4: "Tengo X años" / "Vivo en X" / "Soy de X"
            age_pat = r"\btengo\s+(\d+)\s+años"
            m = re.search(age_pat, user_input, re.IGNORECASE)
            if m:
                age = m.group(1)
                sem.add_entity("usuario", "person", {"age": age})
                sem.add_relation("usuario", "tiene_edad", f"{age}_años")
                logger.info("semantic_fact_extracted", type="age", value=age)

            city_pat = r"\b(?:vivo en|nací en|vengo de)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)"
            m = re.search(city_pat, user_input, re.IGNORECASE)
            if m:
                city = m.group(1).strip().rstrip(".,;")
                if city and len(city) >= 2:
                    sem.add_entity(city.lower(), "place")
                    sem.add_relation("usuario", "vive_en", city.lower())
                    logger.info("semantic_fact_extracted", type="city", value=city)

            # Patrón 5: Proyectos y temas activos
            # "Mi proyecto es X" / "Estoy trabajando en X" / "Guarda este plan de X"
            project_patterns = [
                r"\b(?:mi proyecto es|estoy trabajando en|estoy desarrollando)\s+(.+?)(?:\.|,|$)",
                r"\b(?:guarda|recuerda|anota)\s+(?:este\s+)?(?:plan|proyecto|idea)\s+(?:de\s+|sobre\s+)?(.+?)(?:\.|,|$)",
                r"\b(?:retoma|continúa|sigue con)\s+(?:el\s+)?(?:plan|proyecto)\s+(?:de\s+)?(.+?)(?:\.|,|$)",
            ]
            for pat in project_patterns:
                m = re.search(pat, user_input, re.IGNORECASE)
                if m:
                    project = m.group(1).strip().rstrip(".,;").lower()
                    if project and len(project) >= 3:
                        sem.add_entity(project, "project")
                        sem.add_relation("usuario", "tiene_proyecto", project)
                        logger.info("semantic_fact_extracted", type="project", value=project)
                        break

        except Exception as e:
            logger.warning("semantic_extraction_failed", error=str(e))

    def _query_semantic_for_context(self, user_input: str) -> str | None:
        """Consulta el grafo semántico para construir el contexto que EIDOS
        le pasa al LLM.

        Devuelve SOLO hechos confirmados (no conversaciones pasadas).
        Si hay múltiples nombres (por datos antiguos), devuelve el último.
        """
        if self._memory is None:
            return None
        try:
            sem = self._memory.semantic
            user_entity = sem.get_entity("usuario")
            if user_entity is None:
                return None

            input_lower = user_input.lower()
            facts: list[str] = []
            all_rels = sem.query_relations("usuario", direction="out")

            # ¿Pregunta por su nombre? -> devolver SOLO el último registrado
            if any(p in input_lower for p in ["cómo me llamo", "mi nombre", "quién soy", "cómo te llamas", "recuerdas mi nombre", "quién soy yo"]):
                name_rels = [r for r in all_rels if r.get("predicate") == "tiene_nombre"]
                if name_rels:
                    name_val = name_rels[-1].get("dst", "").replace("_", " ").title()
                    facts.append(f"Te llamas {name_val}")

            # ¿Pregunta por su profesión?
            if any(p in input_lower for p in ["a qué me dedico", "mi trabajo", "mi profesión", "qué hago", "quién soy"]):
                prof_rels = [r for r in all_rels if r.get("predicate") == "tiene_profesion"]
                for r in prof_rels:
                    facts.append(f"Te dedicas a {r.get('dst', '')}")

            # ¿Pregunta por sus preferencias?
            if any(p in input_lower for p in ["qué me gusta", "mis gustos", "mis preferencias"]):
                for r in all_rels:
                    if r.get("predicate") in ("le_gusta", "prefiere", "odia", "le_apasiona"):
                        pred_map = {
                            "le_gusta": "te gusta",
                            "prefiere": "prefieres",
                            "odia": "odias",
                            "le_apasiona": "te apasiona",
                        }
                        pred_str = pred_map.get(r["predicate"], r["predicate"])
                        facts.append(f"Te {pred_str} {r.get('dst', '')}")

            # ¿Pregunta por su edad?
            if any(p in input_lower for p in ["cuántos años", "mi edad"]):
                for r in all_rels:
                    if r.get("predicate") == "tiene_edad":
                        facts.append(f"Tienes {r.get('dst', '').replace('_años', '')} años")

            # ¿Pregunta por dónde vive?
            if any(p in input_lower for p in ["dónde vivo", "dónde nací", "de dónde soy"]):
                for r in all_rels:
                    if r.get("predicate") == "vive_en":
                        facts.append(f"Vives en {r.get('dst', '').title()}")

            # Si no preguntó nada específico pero hay datos, incluirlos como contexto general
            if not facts and any(p in input_lower for p in ["qué sabes", "qué recuerdas", "qué sabes de mí"]):
                for r in all_rels:
                    if r.get("predicate") == "tiene_nombre":
                        name_val = r.get("dst", "").replace("_", " ").title()
                        facts.append(f"Te llamas {name_val}")
                    elif r.get("predicate") == "tiene_profesion":
                        facts.append(f"Te dedicas a {r.get('dst', '')}")
                    elif r.get("predicate") == "vive_en":
                        facts.append(f"Vives en {r.get('dst', '').title()}")
                    elif r.get("predicate") == "tiene_proyecto":
                        facts.append(f"Tienes un proyecto: {r.get('dst', '')}")

            # Incluir proyectos activos en cualquier consulta contextual
            proj_rels = [r for r in all_rels if r.get("predicate") == "tiene_proyecto"]
            if proj_rels and not facts:
                for r in proj_rels:
                    facts.append(f"Proyecto activo: {r.get('dst', '')}")

            if facts:
                return "; ".join(facts)
        except Exception:
            pass
        return None

    @staticmethod
    def _render_response(
        monologue: Monologue,
        route: Route,
        memory_context: list[dict[str, Any]] | None,
    ) -> str:
        """Renderiza la respuesta final que el usuario ve en el chat.

        Si el monologue tiene un campo 'response' (generado por el LLM),
        usa esa respuesta conversacional natural. Si no (stub backend),
        formatea los campos del monólogo como fallback.
        """
        route_str = route.route_type.value
        header = f"[EIDOS · backend={monologue.backend} · route={route_str} · conf={monologue.confidence:.2f}]"

        # Si el LLM generó una respuesta conversacional, usarla.
        if monologue.response and monologue.response.strip():
            body = f"\n{monologue.response.strip()}\n"
        else:
            # Fallback: formatear el monólogo (modo stub o LLM sin campo response).
            plan_str = "\n  - ".join(monologue.plan)
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
