"""Monólogo Interno de EIDOS — Fase 1.1.

El MonologueGenerator produce un "pensamiento estructurado" (Chain-of-Thought)
antes de que EIDOS responda o actúe. El esquema es **rígido** (JSON forzado)
para compensar la debilidad de los modelos pequeños —neuro-simbólico puro.

El monólogo SIEMPRE se persiste en data/monologues/<uuid>.json para que la
capa metacognitiva (Fase 1.3) pueda responder a "¿por qué decidí X?".

Backends:
- "stub":      generador determinista sintético (Fase 1.x, sin GPU).
- "llama_cpp": Qwen2.5-3B local con JSON mode / GBNF (Fase 2).
- "api":       fallback externo (Fase 2.3).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Schema del Monólogo — la "estructura del pensamiento" de EIDOS
# ---------------------------------------------------------------------------


class Monologue(BaseModel):
    """Pensamiento estructurado de EIDOS.

    Inmutable por diseño: una vez emitido, el monólogo es la traza auditable
    de una decisión. La capa metacognitiva lo indexa para auto-evaluación.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID v4 único. Sirve de clave primaria en metacognitive layer.",
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC exacto de emisión. Vital para replay temporal.",
    )

    # --- Input ---
    input_summary: str = Field(
        ...,
        description="Resumen comprimido del input que disparó el monólogo.",
        min_length=1,
        max_length=500,
    )

    # --- CoT estructurado ---
    observation: str = Field(
        ...,
        description="Qué percibe EIDOS del input + contexto.",
        min_length=1,
        max_length=1000,
    )

    hypothesis: str = Field(
        ...,
        description="Hipótesis principal sobre la intención del usuario o la mejor ruta.",
        min_length=1,
        max_length=1000,
    )

    plan: list[str] = Field(
        ...,
        description="Pasos ordenados que EIDOS planea ejecutar. Máx 5 (configurable).",
        min_length=1,
        max_length=10,
    )

    risk: str = Field(
        ...,
        description="Riesgo identificado de la hipótesis/plan. 'none' si no hay.",
        max_length=500,
    )

    confidence: float = Field(
        ...,
        description="Confianza interna en la hipótesis [0.0, 1.0]. < threshold → delegar.",
        ge=0.0,
        le=1.0,
    )

    # --- Respuesta conversacional natural (Fase 6.1) ---
    # Generada por el LLM junto con el monólogo. Es lo que el usuario
    # ve en el chat como respuesta. Si es None, se usa el render formateado.
    response: str | None = Field(
        default=None,
        description="Respuesta conversacional natural para el usuario.",
        max_length=2000,
    )

    # --- Metadatos del backend ---
    backend: Literal["stub", "llama_cpp", "api", "eidos_direct"] = Field(
        ...,
        description="Qué generador produjo este monólogo. Útil para debugging.",
    )

    @field_validator("plan")
    @classmethod
    def _plan_no_empty_steps(cls, v: list[str]) -> list[str]:
        if any(not step.strip() for step in v):
            raise ValueError("Plan steps cannot be empty or whitespace-only.")
        return v

    def to_json_file(self, dir_path: Path) -> Path:
        """Persiste el monólogo como JSON. Devuelve la ruta del archivo.

        Vital para la traza metacognitiva (Fase 1.3).
        """
        dir_path.mkdir(parents=True, exist_ok=True)
        out = dir_path / f"{self.id}.json"
        out.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return out


# ---------------------------------------------------------------------------
# Protocolo de backend — cualquier generador lo implementa
# ---------------------------------------------------------------------------


class MonologueBackend(Protocol):
    """Contrato que todo backend de monólogo debe cumplir."""

    def generate(self, user_input: str, context: str | None = None) -> Monologue:
        """Produce un Monologue a partir del input + contexto opcional."""
        ...


# ---------------------------------------------------------------------------
# Backend Stub — determinista, sin GPU, para desarrollo Fase 1.x
# ---------------------------------------------------------------------------


class StubMonologueBackend:
    """Backend sintético que produce monólogos VÁLIDOS de forma determinista.

    No usa LLM. Heurísticas simples:
    - Detecta pregunta / comando / declaración por signos de puntuación.
    - Extrae keywords (top-N palabras no-stopword).
    - Plan genérico según tipo detectado.
    - Confidence basada en longitud y presencia de keywords reconocidos.

    Es determinista: mismo input → mismo monólogo (clave para tests).
    """

    # Stopwords mínimas, suficientes para el stub. No depende de NLTK.
    _STOPWORDS_ES = frozenset(
        {
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            "y", "o", "de", "del", "a", "en", "que", "es", "por",
            "con", "para", "su", "sus", "lo", "al", "me", "te", "se",
            "le", "les", "no", "si", "como", "más", "muy", "ya",
        }
    )

    def generate(self, user_input: str, context: str | None = None) -> Monologue:
        text = (user_input or "").strip()
        if not text:
            raise ValueError("user_input cannot be empty")

        intent = self._detect_intent(text)
        keywords = self._extract_keywords(text)
        confidence = self._heuristic_confidence(text, keywords)
        plan = self._build_plan(intent, keywords)
        risk = self._assess_risk(intent, confidence)

        return Monologue(
            input_summary=text[:500],
            observation=(
                f"Input recibido ({len(text)} chars, intent='{intent.value}'). "
                f"Keywords detectadas: {', '.join(keywords) or 'ninguna'}. "
                f"Contexto previo: {'sí' if context else 'no'}."
            ),
            hypothesis=(
                f"El usuario probablemente busca {intent.value} sobre "
                f"'{keywords[0] if keywords else 'tema sin keyword clara'}'. "
                f"Convendría {self._intent_action(intent)} manteniendo tono claro."
            ),
            plan=plan,
            risk=risk,
            confidence=confidence,
            response=(
                f"(Modo stub — sin IA real) He recibido tu mensaje sobre "
                f"'{keywords[0] if keywords else 'tu consulta'}'. "
                f"Para que pueda responderte properly, configura un cerebro en ⚙️ Settings."
            ),
            backend="stub",
        )

    # --- heurísticas internas ---

    @staticmethod
    def _detect_intent(text: str) -> _Intent:
        t = text.rstrip()
        if t.endswith("?") or t.startswith(("qué ", "que ", "cómo ", "como ", "por qué ", "¿")):
            return _Intent.QUESTION
        if any(t.lower().startswith(v) for v in ("crea ", "crea", "haz ", "haz", "ejecuta ", "genera ", "borra ")):
            return _Intent.COMMAND
        return _Intent.STATEMENT

    def _extract_keywords(self, text: str, top_n: int = 5) -> list[str]:
        # Limpieza mínima: minúsculas, strip de puntuación básica.
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower())
        tokens = [w for w in cleaned.split() if w not in self._STOPWORDS_ES and len(w) >= 3]
        # Preservar orden de aparición, deduplicar.
        seen: set[str] = set()
        keywords: list[str] = []
        for tok in tokens:
            if tok not in seen:
                seen.add(tok)
                keywords.append(tok)
            if len(keywords) >= top_n:
                break
        return keywords

    @staticmethod
    def _heuristic_confidence(text: str, keywords: list[str]) -> float:
        # Base baja. Sube con keywords claras y longitud moderada.
        score = 0.4
        if keywords:
            score += min(0.05 * len(keywords), 0.25)
        if 10 <= len(text) <= 300:
            score += 0.15
        elif len(text) > 300:
            score -= 0.05  # input largo = más ambigüedad
        # Pregunta directa con keyword → más confianza
        if text.rstrip().endswith("?") and keywords:
            score += 0.10
        return round(max(0.0, min(1.0, score)), 2)

    @staticmethod
    def _build_plan(intent: _Intent, keywords: list[str]) -> list[str]:
        topic = keywords[0] if keywords else "el tema solicitado"
        if intent is _Intent.QUESTION:
            return [
                f"Recuperar contexto previo sobre '{topic}' en memoria episódica.",
                f"Formular respuesta concisa sobre '{topic}'.",
                "Verificar consistencia con capa semántica.",
                "Persistir interacción en memoria episódica.",
            ]
        if intent is _Intent.COMMAND:
            return [
                f"Identificar acción solicitada sobre '{topic}'.",
                "Validar permisos y safety de la acción.",
                f"Ejecutar acción o delegar al Cortex Hub si requiere inferencia.",
                "Reportar resultado al usuario.",
                "Persistir outcome en memoria episódica.",
            ]
        return [
            f"Acknowledge sobre '{topic}'.",
            "Actualizar grafo semántico si hay nueva información.",
            "Persistir en memoria episódica.",
        ]

    @staticmethod
    def _assess_risk(intent: _Intent, confidence: float) -> str:
        if confidence < 0.5:
            return "Confianza baja; conviene pedir aclaración al usuario."
        if intent is _Intent.COMMAND:
            return "Comando detectado; validar safety antes de ejecutar."
        return "none"

    @staticmethod
    def _intent_action(intent: _Intent) -> str:
        return {
            _Intent.QUESTION: "responder",
            _Intent.COMMAND: "actuar",
            _Intent.STATEMENT: "acknowledge",
        }[intent]


# ---------------------------------------------------------------------------
# Enum privado para clasificación de intención
# ---------------------------------------------------------------------------

from enum import Enum


class _Intent(str, Enum):
    QUESTION = "question"
    COMMAND = "command"
    STATEMENT = "statement"


# ---------------------------------------------------------------------------
# Generador público — fachada que selecciona backend según config
# ---------------------------------------------------------------------------


class MonologueGenerator:
    """Fachada que produce monólogos usando el backend configurado.

    Uso:
        gen = MonologueGenerator(backend="stub")
        m = gen.generate("¿Qué es EIDOS?")
        print(m.plan)

    Fase 2: se puede inyectar una instancia ya construida del backend
    vía `backend_instance` (útil cuando CortexHub ya ha cargado el modelo).
    """

    def __init__(
        self,
        backend: Literal["stub", "llama_cpp", "api"] = "stub",
        *,
        monologues_dir: Path | None = None,
        max_plan_steps: int = 5,
        backend_instance: MonologueBackend | None = None,
    ) -> None:
        self._backend_name = backend
        self._max_plan_steps = max_plan_steps
        self._monologues_dir = monologues_dir
        if backend_instance is not None:
            self._backend = backend_instance
        else:
            self._backend = self._select_backend(backend)

    @staticmethod
    def _select_backend(name: str) -> MonologueBackend:
        if name == "stub":
            return StubMonologueBackend()
        if name == "llama_cpp":
            # Fase 2: import eidos.cortex.llama_backend
            raise NotImplementedError("llama_cpp backend arrives in Phase 2.")
        if name == "api":
            # Fase 2.3: fallback externo
            raise NotImplementedError("api backend arrives in Phase 2.3.")
        raise ValueError(f"Unknown monologue backend: {name}")

    def generate(self, user_input: str, context: str | None = None) -> Monologue:
        """Genera, valida y (opcionalmente) persiste el monólogo."""
        monologue = self._backend.generate(user_input, context)

        # Truncar plan si excede max_plan_steps (defensivo).
        if len(monologue.plan) > self._max_plan_steps:
            monologue = monologue.model_copy(update={"plan": monologue.plan[: self._max_plan_steps]})

        # Persistencia — traza metacognitiva (CRÍTICO).
        if self._monologues_dir is not None:
            monologue.to_json_file(self._monologues_dir)

        return monologue

    @property
    def backend_name(self) -> str:
        return self._backend_name


__all__ = [
    "Monologue",
    "MonologueBackend",
    "MonologueGenerator",
    "StubMonologueBackend",
]
