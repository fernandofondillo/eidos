"""EvolutionLoop — Fase 3.3.

Ciclo de autoevolución: EIDOS detecta cuando necesita una cápsula que
no existe, la forja, la valida y la persiste. También promueve
cápsulas populares a favoritas automáticamente.

Detección de necesidad (heurísticas):
1. El usuario pide explícitamente: "conviértete en experto en X"
   o "necesito que seas experto en X".
2. El monólogo indica route_type=respond_direct pero la hipótesis
   contiene "necesito experto" o "falta especialización".
3. (Futuro) Tras N turnos sobre el mismo tema sin cápsula apropiada.

Promoción a favorita:
- Si una cápsula (no favorita) se usa >= PROMOTION_USES_THRESHOLD veces
  en PROMOTION_WINDOW_HOURS, se promueve a favorite=True automáticamente.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eidos.core.forge import CapsuleForge, ForgeDecision
from eidos.core.monologue import Monologue
from eidos.memory.procedural import ProceduralMemory
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# Patrones NL que indican petición EXPLÍCITA de especialización.
# Solo se disparan con frases completas, no con palabras sueltas.
_SPECIALIZATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:convi[eé]rtete\s+en|transf[oó]rmate\s+en|vu[eé]lvete\s+en)\s+(?:un\s+|una\s+)?experto\s+en\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:necesito|quiero)\s+que\s+(?:seas|te\s+conviertas)\s+(?:un\s+|una\s+)?experto\s+en\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:crea|genera|forja)\s+(?:una\s+)?(?:c[oá]psula|especializaci[oó]n)\s+(?:para|de|en)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:act[uú]a\s+como|asume\s+el\s+rol\s+de)\s+(?:un\s+|una\s+)?experto\s+en\s+(.+)", re.IGNORECASE),
    re.compile(r"especial[ií]zate\s+en\s+(.+)", re.IGNORECASE),
    re.compile(r"quiero\s+que\s+seas\s+experto\s+en\s+(.+)", re.IGNORECASE),
]

# Lista negra de palabras que NUNCA deben generar cápsulas.
# Si el tema detectado es una de estas palabras, NO se crea la cápsula.
_BLACKLIST_TOPICS = frozenset({
    "hola", "julio", "eres", "esta", "este", "búsqueda", "internet",
    "general", "eidos", "recuerdas", "como", "qué", "quién", "dónde",
    "cuándo", "por", "para", "con", "sin", "sobre", "después", "antes",
    "hoy", "ayer", "ahora", "luego", "aquí", "allí", "todo", "nada",
    "algo", "alguien", "nadie", "brent", "cotización", "precio",
    "dame", "dime", "haz", "voy", "tengo", "quiero", "necesito",
    "puedes", "puede", "ser", "estar", "tener", "hacer", "decir",
    "ver", "dar", "saber", "querer", "pensar", "creer", "sentir",
    "vivir", "morir", "abrir", "cerrar", "fue", "fui", "era", "es",
    "son", "han", "has", "hay", "más", "menos", "muy", "poco", "mucho",
    "siempre", "nunca", " jamás", "también", "tampoco", "sí", "no",
    "ok", "vale", "bien", "mal", "perfecto", "genial", "gracias",
})


class EvolutionLoop:
    """Detecta necesidades de especialización y forja cápsulas automáticamente.

    No es un hilo background — se invoca explícitamente desde EidosCore
    tras cada turno del usuario.
    """

    PROMOTION_USES_THRESHOLD = 3
    PROMOTION_WINDOW_HOURS = 24

    def __init__(
        self,
        forge: CapsuleForge,
        procedural: ProceduralMemory,
        auto_forge: bool = True,
    ) -> None:
        self._forge = forge
        self._procedural = procedural
        self._auto_forge = auto_forge

    # ---------------- API pública ----------------

    def detect_need(self, user_input: str, monologue: Monologue | None = None) -> str | None:
        """Detecta si el usuario está pidiendo una nueva especialización.

        Returns:
            La temática detectada (str) o None si no hay petición clara.
        """
        # 1. Patrones NL explícitos en el input del usuario
        for pattern in _SPECIALIZATION_PATTERNS:
            match = pattern.search(user_input)
            if match:
                topic = match.group(1).strip().rstrip(".!,;:")
                # Tema debe ser sustantivo: al menos 2 chars en total
                # (aceptamos "ML", "AI", "Rust" como temas válidos)
                if topic and len(topic) >= 2:
                    return topic

        # 2. Heurística basada en monólogo (opcional)
        if monologue is not None:
            hypothesis_lower = monologue.hypothesis.lower()
            if any(k in hypothesis_lower for k in ("necesito experto", "falta especialización", "crear cápsula")):
                # Extraer keywords del input (tema completo, no tokens individuales)
                # Buscar el último sustantivo significativo
                cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in user_input.lower())
                tokens = [w for w in cleaned.split() if len(w) >= 2]
                # Tomar hasta 3 tokens finales como tema
                if tokens:
                    return " ".join(tokens[-3:])

        return None

    def process_turn(
        self,
        user_input: str,
        monologue: Monologue | None = None,
    ) -> dict[str, Any] | None:
        """Procesa un turno del usuario. Si detecta necesidad, forja cápsula.

        Returns:
            None si no se forjó nada; dict con info del forge si sí.
        """
        topic = self.detect_need(user_input, monologue)
        if topic is None:
            return None

        if not self._auto_forge:
            logger.info("evolution_need_detected_but_auto_forge_disabled", topic=topic)
            return {"topic": topic, "auto_forge_disabled": True}

        # Forjar la cápsula
        try:
            draft, decision = self._forge.forge(
                request=topic,
                context={"requested_by": "auto_evolution"},
            )
            logger.info(
                "evolution_capsule_forged",
                topic=topic,
                draft_id=draft.id,
                decision=decision.value,
            )
            return {
                "topic": topic,
                "draft_id": draft.id,
                "name": draft.name,
                "decision": decision.value,
                "confidence": draft.genesis_confidence,
                "smoke_test_passed": draft.smoke_test_passed,
            }
        except Exception as e:
            logger.error("evolution_forge_failed", topic=topic, error=str(e))
            return {"topic": topic, "error": str(e)}

    def check_promotions(self) -> list[str]:
        """Revisa todas las cápsulas no-favoritas y promueve las que cumplen
        el criterio (uses >= threshold en ventana de tiempo).

        Returns:
            Lista de IDs de cápsulas promovidas.
        """
        promoted: list[str] = []
        all_caps = self._procedural.list_all(include_expired=False)
        now = datetime.now(timezone.utc)

        for cap in all_caps:
            if cap.favorite:
                continue
            if cap.uses < self.PROMOTION_USES_THRESHOLD:
                continue
            # Verificar que los usos son recientes (dentro de la ventana)
            if cap.last_used is None:
                continue
            try:
                last_used = datetime.fromisoformat(cap.last_used.replace("Z", "+00:00"))
            except ValueError:
                continue
            if (now - last_used).total_seconds() > self.PROMOTION_WINDOW_HOURS * 3600:
                continue

            # Promover
            self._procedural.set_favorite(cap.id, True)
            promoted.append(cap.id)
            logger.info(
                "capsule_promoted_to_favorite",
                id=cap.id,
                name=cap.name,
                uses=cap.uses,
            )

        return promoted

    def stats(self) -> dict[str, Any]:
        all_caps = self._procedural.list_all(include_expired=True)
        favorites = [c for c in all_caps if c.favorite]
        high_use = [c for c in all_caps if c.uses >= self.PROMOTION_USES_THRESHOLD]
        return {
            "module": "evolution",
            "auto_forge_enabled": self._auto_forge,
            "total_capsules": len(all_caps),
            "favorites": len(favorites),
            "promotion_candidates": len([c for c in high_use if not c.favorite]),
            "promotion_threshold": self.PROMOTION_USES_THRESHOLD,
            "promotion_window_hours": self.PROMOTION_WINDOW_HOURS,
        }


__all__ = ["EvolutionLoop"]
