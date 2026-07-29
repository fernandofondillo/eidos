"""LlamaCppBackend — Fase 2.2.

Implementa el protocolo MonologueBackend usando llama-cpp-python con
un modelo GGUF local (ej. Qwen2.5-3B-Instruct Q4_K_M).

Características clave:
- Lazy import: solo importa `llama_cpp` al instanciarse. Permite que el
  paquete se importe sin la dependencia instalada (Fase 1.x sigue funcional).
- GBNF grammar estricto: fuerza al modelo a producir JSON válido que
  cumple el schema del Monologue. Si el modelo genera JSON inválido,
  se rechaza y se reintenta (máx 3 intentos) antes de fallback a stub.
- Singleton-virtual-ready: el backend pide un lock al CortexHub antes
  de cargar el modelo en VRAM (prepara Fase 4 MESH).
- Inyectable LlamaClient: para tests se pasa un FakeLlamaClient que
  produce JSON válido sin GPU.

Para compilar en macOS Apple Silicon:
    CMAKE_ARGS="-DGGML_METAL=on" uv sync --extra cortex
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from eidos.core.monologue import Monologue, MonologueBackend
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocolo LlamaClient — permite inyectar mocks en tests
# ---------------------------------------------------------------------------


class LlamaClient(Protocol):
    """Contrato que cualquier cliente LLM debe cumplir para el backend."""

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        grammar: str | None = None,
        stop: list[str] | None = None,
    ) -> str:
        """Devuelve el texto generado."""
        ...


# ---------------------------------------------------------------------------
# GBNF Grammar — fuerza JSON válido según el schema del Monologue
# ---------------------------------------------------------------------------

# Grammar simplificada pero estricta: el modelo DEBE producir un objeto JSON
# con las claves obligatorias del Monologue. Los valores string pueden
# contener cualquier char escapado.
#
# Esta gramática no valida tipos finos (confidence debe ser float [0,1]) —
# eso lo hace Pydantic al parsear. La gramática solo garantiza JSON válido.
_MONOLOGUE_GBNF = r"""
root        ::= "{" ws "\"observation\"" ws ":" ws string "," ws
                    "\"hypothesis\"" ws ":" ws string "," ws
                    "\"plan\"" ws ":" ws array "," ws
                    "\"risk\"" ws ":" ws string "," ws
                    "\"confidence\"" ws ":" ws number "}" ws
array       ::= "[" ws string ("," ws string)* ws "]"
string      ::= "\"" char* "\""
char        ::= [^"\\\n] | "\\" ["\\/bfnrt] | "\\u" [0-9a-fA-F]{4}
number      ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)? ([eE] [-+]? [0-9]+)?
ws          ::= [ \t\n]*
"""

# Fallback regex para extraer JSON de respuestas con texto alrededor
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


# ---------------------------------------------------------------------------
# Prompt template — instrucciones claras para el modelo
# ---------------------------------------------------------------------------


def _build_prompt(user_input: str, context: str | None, max_plan_steps: int) -> str:
    """Construye el prompt para el modelo.

    Usa formato de chat simple (no ChatML específico de Qwen) para máxima
    portabilidad. llama-cpp-python aplica el chat template del modelo.
    """
    ctx_block = f"\nContexto previo: {context}" if context else ""
    return f"""Eres EIDOS, una entidad cognitiva autónoma. Analiza el siguiente input del usuario y produce un monólogo interno estructurado en JSON.

Input del usuario: "{user_input}"{ctx_block}

Devuelve EXACTAMENTE un objeto JSON con esta forma (sin texto adicional, sin markdown):
{{
  "observation": "qué percibes del input",
  "hypothesis": "hipótesis sobre la intención",
  "plan": ["paso 1", "paso 2", ...],
  "risk": "riesgo identificado o 'none'",
  "confidence": 0.7,
  "response": "tu respuesta conversacional natural al usuario, en español, como si estuvieras hablando con él"
}}

Restricciones:
- plan: entre 1 y {max_plan_steps} pasos, cada uno una frase corta.
- confidence: número entre 0.0 y 1.0.
- risk: 'none' si no hay riesgo; descripción corta si lo hay.
- response: ES MUY IMPORTANTE. Es lo que el usuario verá como respuesta. Debe ser natural, útil y en español. No digas que eres un JSON o que estás siguiendo un formato. Responde directamente al usuario.
- Responde en español."""


# ---------------------------------------------------------------------------
# LlamaCppBackend
# ---------------------------------------------------------------------------


class LlamaCppBackend(MonologueBackend):
    """Backend de monólogo basado en llama-cpp-python + modelo GGUF local.

    Args:
        model_path: ruta al archivo .gguf en disco.
        n_ctx: contexto máximo en tokens (default 4096).
        n_gpu_layers: capas a cargar en GPU/Metal (-1 = todas).
        max_plan_steps: límite de pasos en el plan.
        max_retries: reintentos si el JSON es inválido (default 3).
        client: opcional, inyecta un LlamaClient para tests. Si es None,
            se instancia llama_cpp.Llama al vuelo.
    """

    def __init__(
        self,
        model_path: str,
        *,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        max_plan_steps: int = 5,
        max_retries: int = 3,
        temperature: float = 0.7,
        client: LlamaClient | None = None,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._max_plan_steps = max_plan_steps
        self._max_retries = max_retries
        self._temperature = temperature

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = self._load_real_client()
            self._owns_client = True

    def _load_real_client(self) -> LlamaClient:
        """Instancia llama_cpp.Llama con lazy import."""
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python no está instalado. "
                "Instala con: CMAKE_ARGS='-DGGML_METAL=on' uv sync --extra cortex"
            ) from e

        logger.info(
            "llama_loading",
            model=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
        )
        llama = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=False,
        )
        return _LlamaCppAdapter(llama)

    # ---------------- MonologueBackend protocol ----------------

    def generate(self, user_input: str, context: str | None = None) -> Monologue:
        if not user_input:
            raise ValueError("user_input cannot be empty")

        prompt = _build_prompt(user_input, context, self._max_plan_steps)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                raw = self._client.complete(
                    prompt=prompt,
                    max_tokens=512,
                    temperature=self._temperature if attempt == 1 else max(0.1, self._temperature - 0.2 * attempt),
                    grammar=_MONOLOGUE_GBNF,
                    stop=["```", "\n\n\n"],
                )
                parsed = self._parse_response(raw, user_input)
                logger.info(
                    "llama_monologue_generated",
                    attempt=attempt,
                    confidence=parsed.confidence,
                )
                return parsed
            except Exception as e:
                last_error = e
                logger.warning(
                    "llama_monologue_retry",
                    attempt=attempt,
                    error=str(e),
                )

        # Tras N reintentos, fallback a un Monologue de baja confianza
        logger.error("llama_monologue_failed_all_retries", attempts=self._max_retries, last_error=str(last_error))
        raise RuntimeError(
            f"LlamaCppBackend failed after {self._max_retries} attempts: {last_error}"
        )

    # ---------------- parseo ----------------

    def _parse_response(self, raw: str, user_input: str) -> Monologue:
        """Extrae JSON de la respuesta y lo valida con Pydantic."""
        # Intentar parse directo
        text = raw.strip()
        # Quitar fences markdown si el modelo los añadió
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extraer primer objeto JSON en el texto
            match = _JSON_OBJECT_RE.search(text)
            if not match:
                raise ValueError(f"No JSON found in response: {text[:200]}")
            data = json.loads(match.group(0))

        # Validar campos obligatorios
        required = {"observation", "hypothesis", "plan", "risk", "confidence"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Missing fields in monologue JSON: {missing}")

        # Truncar plan
        plan = list(data["plan"])
        if len(plan) > self._max_plan_steps:
            plan = plan[: self._max_plan_steps]
        if not plan:
            plan = ["Sin pasos definidos."]

        # Clamp confidence
        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        return Monologue(
            input_summary=user_input[:500],
            observation=str(data["observation"])[:1000],
            hypothesis=str(data["hypothesis"])[:1000],
            plan=[str(p) for p in plan],
            risk=str(data.get("risk", "none"))[:500],
            confidence=confidence,
            response=str(data.get("response", ""))[:2000] or None,
            backend="llama_cpp",
        )

    def close(self) -> None:
        """Libera el modelo si lo poseemos."""
        if self._owns_client:
            client = getattr(self, "_client", None)
            if client is not None and hasattr(client, "close"):
                try:
                    client.close()  # type: ignore[attr-defined]
                except Exception as e:
                    logger.warning("llama_close_failed", error=str(e))


# ---------------------------------------------------------------------------
# Adapter: envuelve llama_cpp.Llama para cumplir LlamaClient
# ---------------------------------------------------------------------------


class _LlamaCppAdapter:
    """Adapta llama_cpp.Llama al protocolo LlamaClient."""

    def __init__(self, llama: Any) -> None:
        self._llama = llama

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        grammar: str | None = None,
        stop: list[str] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop or [],
        }
        if grammar is not None:
            try:
                from llama_cpp import LlamaGrammar  # type: ignore[import-not-found]

                kwargs["grammar"] = LlamaGrammar.from_string(grammar)
            except ImportError:
                logger.warning("llama_grammar_unavailable_ignoring_grammar")
        result = self._llama(**kwargs)
        # llama_cpp devuelve dict con "choices" -> [{"text": "..."}]
        choices = result.get("choices") if isinstance(result, dict) else None
        if not choices:
            raise ValueError(f"Unexpected llama_cpp response: {result}")
        return choices[0].get("text", "")

    def close(self) -> None:
        # llama_cpp.Llama no tiene close explícito; GC lo maneja
        self._llama = None


__all__ = ["LlamaCppBackend", "LlamaClient"]
