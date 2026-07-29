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

        # 0a. Reward de satisfacción (solo positiva — tras 3 turnos neutros)
        # Ya NO penalizamos por el input del usuario (generaba falsos negativos
        # cuando el usuario citaba a EIDOS diciendo "no tengo memoria" etc.).
        # Solo damos recompensas positivas por racha de turnos sin corrección.
        reward_delta = 0.0
        if self._motivation is not None:
            try:
                # Solo observar para racha positiva — sin penalización negativa.
                # Pasamos un input "neutro" para que no dispare negativos.
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

        # 1. Pensar — EIDOS construye el contexto para el LLM (su "sentido")
        # El LLM SOLO recibe hechos confirmados del grafo semántico.
        # NO recibe conversaciones episódicas crudas (pueden estar contaminadas
        # o ser de otra sesión). EIDOS es quien piensa; el LLM es el sentido.
        full_context = context or ""
        if self._memory is not None:
            # Consultar SOLO memoria semántica (hechos confirmados del usuario)
            sem_ctx = self._query_semantic_for_context(user_input)
            if sem_ctx:
                full_context = (full_context + "\n" if full_context else "") + sem_ctx
            # NO inyectar memoria episódica cruda al LLM.
            # La memoria episódica se usa internamente para routing (search_memory)
            # pero no se pasa al LLM como contexto, para evitar contaminación.

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

        # 5. Responder (template; NLG real en Fase 2)
        # Consultar memoria semántica para enriquecer la respuesta
        semantic_context = None
        if self._memory is not None:
            semantic_context = self._query_semantic_for_context(user_input)

        text = self._render_response(monologue, route, memory_context)

        # Si hay contexto semántico (ej: "Te llamas Fernando"), añadirlo a la respuesta
        if semantic_context:
            text += f"\n\n💡 {semantic_context}"

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
        """Extrae hechos simples del input del usuario y los guarda en el grafo semántico.

        Heurística basada en patrones NL comunes en español. No es perfecta,
        pero permite que EIDOS recuerda nombres, profesiones y preferencias
        sin necesidad de un LLM para la extracción.

        Ahora también extrae de la respuesta del LLM (que suele confirmar
        el nombre del usuario en frases como "Encantado, Fernando").
        """
        import re

        if self._memory is None:
            return
        try:
            sem = self._memory.semantic

            # Combinar input + respuesta para extracción
            combined_text = f"{user_input} {response}"

            # Patrón 1: "Me llamo X" / "Soy X" / "Mi nombre es X"
            name_patterns = [
                r"\b(?:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)",
                r"\b(?:encantado|hola)\s*,?\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",  # "Encantado, Fernando"
            ]
            for pat in name_patterns:
                m = re.search(pat, combined_text, re.IGNORECASE)
                if m:
                    name = m.group(1).strip().rstrip(".,;")
                    # Capitalizar primera letra
                    name = name[0].upper() + name[1:] if name else name
                    # Filtrar palabras que no son nombres
                    if name and len(name) >= 2 and name.lower() not in {
                        "yo", "tu", "el", "ella", "eso", "este", "aqui",
                        "ahora", "hoy", "ayer", "luego", "despues",
                    }:
                        sem.add_entity("usuario", "person", {"name": name})
                        sem.add_relation("usuario", "tiene_nombre", name.lower().replace(" ", "_"))
                        logger.info("semantic_fact_extracted", type="name", value=name)
                        break

            # Patrón 2: "Soy [profesión]" / "Trabajo como X" / "Me dedico a X"
            prof_patterns = [
                r"\bsoy\s+(\w+(?:\s+\w+)?)",
                r"\btrabajo como\s+(\w+(?:\s+\w+)?)",
                r"\bme dedico a\s+(?:la\s+|el\s+)?(\w+(?:\s+\w+)?)",
                r"\bsoy\s+(\w+(?:\s+\w+)?)(?:\s+de\s|,)",
            ]
            professions = {
                "desarrollador", "programador", "ingeniero", "abogado", "médico",
                "doctor", "profesor", "maestro", "diseñador", "arquitecto",
                "consultor", "analista", "gerente", "director", "empresario",
                "periodista", "escritor", "artista", "músico", "fotógrafo",
                "marketing", "ventas", "finanzas", "contador", "economista",
                "coach", "entrenador", "investigador", "científico",
            }
            for pat in prof_patterns:
                m = re.search(pat, combined_text, re.IGNORECASE)
                if m:
                    prof = m.group(1).strip().rstrip(".,;").lower()
                    if prof in professions or (prof and prof not in {
                        "", "yo", "feliz", "alto", "bajo", "aqui", "ahora",
                        "hoy", "ayer", "eso", "este", "la", "el",
                    } and len(prof) >= 4):
                        sem.add_entity("usuario", "person", {"profession": prof})
                        sem.add_relation("usuario", "tiene_profesion", prof)
                        logger.info("semantic_fact_extracted", type="profession", value=prof)
                        break

            # Patrón 3: "Me gusta X" / "Prefiero X" / "Odio X"
            pref_patterns = [
                (r"\bme gusta\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "le_gusta"),
                (r"\bprefiero\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "prefiere"),
                (r"\bodio\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "odia"),
                (r"\bme apasiona\s+(?:el\s+|la\s+|los\s+|las\s+)?(\w+(?:\s+\w+)?)", "le_apasiona"),
            ]
            for pat, pred in pref_patterns:
                m = re.search(pat, combined_text, re.IGNORECASE)
                if m:
                    obj = m.group(1).strip().rstrip(".,;").lower()
                    if obj and len(obj) >= 2 and obj not in {"yo", "tu", "el", "ella", "eso", "este"}:
                        sem.add_entity(obj, "concept")
                        sem.add_relation("usuario", pred, obj)
                        logger.info("semantic_fact_extracted", type="preference", predicate=pred, value=obj)
                        break

            # Patrón 4: "Tengo X años" / "Vivo en X" / "Soy de X"
            age_pat = r"\btengo\s+(\d+)\s+años"
            m = re.search(age_pat, combined_text, re.IGNORECASE)
            if m:
                age = m.group(1)
                sem.add_entity("usuario", "person", {"age": age})
                sem.add_relation("usuario", "tiene_edad", f"{age}_años")
                logger.info("semantic_fact_extracted", type="age", value=age)

            city_pat = r"\b(?:vivo en|nací en|soy de|vengo de)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)"
            m = re.search(city_pat, combined_text, re.IGNORECASE)
            if m:
                city = m.group(1).strip().rstrip(".,;")
                if city and len(city) >= 2:
                    sem.add_entity(city.lower(), "place")
                    sem.add_relation("usuario", "vive_en", city.lower())
                    logger.info("semantic_fact_extracted", type="city", value=city)

        except Exception as e:
            logger.warning("semantic_extraction_failed", error=str(e))

    def _query_semantic_for_context(self, user_input: str) -> str | None:
        """Consulta el grafo semántico para enriquecer el contexto.

        Si el usuario pregunta por su nombre, profesión, etc., esto devuelve
        la información recordada.
        """
        if self._memory is None:
            return None
        try:
            sem = self._memory.semantic
            user_entity = sem.get_entity("usuario")
            if user_entity is None:
                return None

            import re
            input_lower = user_input.lower()

            # Detectar qué está preguntando el usuario
            facts: list[str] = []

            # ¿Pregunta por su nombre?
            if any(p in input_lower for p in ["cómo me llamo", "mi nombre", "quién soy", "cómo te llamas"]):
                rels = sem.query_relations("usuario", direction="out")
                for r in rels:
                    if r.get("predicate") == "tiene_nombre":
                        name_val = r.get("dst", "").replace("_", " ").title()
                        facts.append(f"Te llamas {name_val}")

            # ¿Pregunta por su profesión?
            if any(p in input_lower for p in ["a qué me dedico", "mi trabajo", "mi profesión", "qué hago"]):
                rels = sem.query_relations("usuario", direction="out")
                for r in rels:
                    if r.get("predicate") == "tiene_profesion":
                        facts.append(f"Te dedicas a {r.get('dst', '')}")

            # ¿Pregunta por sus preferencias?
            if any(p in input_lower for p in ["qué me gusta", "mis gustos", "mis preferencias"]):
                rels = sem.query_relations("usuario", direction="out")
                for r in rels:
                    if r.get("predicate") in ("le_gusta", "prefiere", "odia"):
                        pred_str = {"le_gusta": "te gusta", "prefiere": "prefieres", "odia": "odias"}[r["predicate"]]
                        facts.append(f"Te {pred_str} {r.get('dst', '')}")

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
