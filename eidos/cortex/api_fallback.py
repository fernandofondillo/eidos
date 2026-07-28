"""API Fallback — Fase 2.3.

Fallback a APIs externas cuando el Cortex Hub local no está disponible.
SIEMPRE aplica PrivacyFilter antes de cualquier call externa.

Compatible con APIs OpenAI (chat completions):
- OpenAI oficial
- OpenRouter
- Together.ai
- Anyscale
- Cualquier endpoint /v1/chat/completions

Config en config/eidos.yaml:
    cortex:
      api_fallback:
        enabled: false           # opt-in
        base_url: "https://api.openai.com/v1"
        api_key_env: "OPENAI_API_KEY"
        model: "gpt-4o-mini"
        timeout_sec: 30
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from eidos.core.monologue import Monologue, MonologueBackend
from eidos.cortex.llama_backend import _build_prompt, _MONOLOGUE_GBNF
from eidos.cortex.privacy import PrivacyFilter
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class APIFallbackBackend(MonologueBackend):
    """Backend de monólogo vía API externa (compatible OpenAI o Anthropic).

    Soporta dos protocolos:
    - api_type='openai' (default): endpoint /chat/completions con body
      {model, messages, ...}. Compatible con OpenAI, OpenRouter, Together,
      Groq, MiniMax nativa, etc.
    - api_type='anthropic': endpoint /v1/messages con body
      {model, max_tokens, messages, system} y headers x-api-key +
      anthropic-version. Compatible con Anthropic Claude oficial y con
      MiniMax-M3 vía api.minimax.io/anthropic.

    Aplica PrivacyFilter al prompt antes de enviar.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        model: str = "gpt-4o-mini",
        timeout_sec: int = 30,
        max_plan_steps: int = 5,
        max_retries: int = 2,
        privacy_filter: PrivacyFilter | None = None,
        client: Any = None,
        api_type: str = "openai",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or os.environ.get(api_key_env)
        self._api_key_env = api_key_env
        self._model = model
        self._timeout = timeout_sec
        self._max_plan_steps = max_plan_steps
        self._max_retries = max_retries
        self._privacy = privacy_filter or PrivacyFilter()
        # client inyectable para tests
        self._client = client  # callable(payload, headers, url) -> dict
        self._api_type = api_type  # 'openai' | 'anthropic'

        if not self._api_key:
            logger.warning(
                "api_fallback_no_key",
                env_var=api_key_env,
                msg="Calls will fail until the env var is set.",
            )

    def generate(self, user_input: str, context: str | None = None) -> Monologue:
        if not user_input:
            raise ValueError("user_input cannot be empty")

        # 1. Aplicar PrivacyFilter al input y contexto antes de cualquier envío
        filtered_input = self._privacy.filter_str(user_input)
        filtered_context = self._privacy.filter_str(context) if context else None

        if filtered_input != user_input:
            logger.info(
                "api_fallback_privacy_applied",
                original_len=len(user_input),
                filtered_len=len(filtered_input),
            )

        prompt = _build_prompt(filtered_input, filtered_context, self._max_plan_steps)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response_text = self._call_api(prompt)
                parsed = self._parse_response(response_text, user_input)
                # El Monologue guarda el input_summary ORIGINAL (no filtrado)
                # porque es para consumo interno del usuario.
                logger.info("api_fallback_success", attempt=attempt, confidence=parsed.confidence)
                return parsed
            except Exception as e:
                last_error = e
                logger.warning("api_fallback_retry", attempt=attempt, error=str(e))

        raise RuntimeError(f"APIFallback failed after {self._max_retries} attempts: {last_error}")

    def _call_api(self, prompt: str) -> str:
        """Llama al endpoint API según api_type (openai o anthropic)."""
        if self._api_type == "anthropic":
            return self._call_anthropic(prompt)
        return self._call_openai(prompt)

    def _call_openai(self, prompt: str) -> str:
        """Llama al endpoint /chat/completions compatible OpenAI."""
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are EIDOS, a cognitive entity. Respond ONLY with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 512,
            # Algunos providers soportan response_format json; lo intentamos.
            "response_format": {"type": "json_object"},
        }

        if self._client is not None:
            # Test mode
            return self._client(payload, self._headers(), self._url)

        if not self._api_key:
            raise RuntimeError(
                f"API key not set. Configure env var {self._api_key_env} or pass api_key."
            )

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                choices = body.get("choices", [])
                if not choices:
                    raise ValueError(f"No choices in API response: {body}")
                return choices[0].get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API HTTP {e.code}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"API network error: {e}") from e

    def _call_anthropic(self, prompt: str) -> str:
        """Llama al endpoint /v1/messages compatible Anthropic.

        Usado por Anthropic Claude oficial y por MiniMax-M3 vía
        api.minimax.io/anthropic.
        """
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": "You are EIDOS, a cognitive entity. Respond ONLY with valid JSON.",
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        if self._client is not None:
            # Test mode — el mock devuelve texto igual que OpenAI
            return self._client(payload, self._headers(), self._url)

        if not self._api_key:
            raise RuntimeError(
                f"API key not set. Configure env var {self._api_key_env} or pass api_key."
            )

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                # Anthropic devuelve {content: [{type: "text", text: "..."}]}
                content_blocks = body.get("content", [])
                if not content_blocks:
                    raise ValueError(f"No content in Anthropic response: {body}")
                # Concatenar todos los bloques de texto
                texts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return "".join(texts)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API HTTP {e.code}: {body[:300]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Anthropic API network error: {e}") from e

    @property
    def _url(self) -> str:
        if self._api_type == "anthropic":
            return f"{self._base_url}/v1/messages"
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        if self._api_type == "anthropic":
            # Anthropic usa x-api-key + anthropic-version
            return {
                "Content-Type": "application/json",
                "x-api-key": self._api_key or "",
                "anthropic-version": "2023-06-01",
            }
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key or ''}",
        }

    def _parse_response(self, raw: str, user_input: str) -> Monologue:
        """Reutiliza la lógica de LlamaCppBackend."""
        from eidos.cortex.llama_backend import _JSON_OBJECT_RE

        text = raw.strip()
        if text.startswith("```"):
            import re

            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_OBJECT_RE.search(text)
            if not match:
                raise ValueError(f"No JSON found in response: {text[:200]}")
            data = json.loads(match.group(0))

        required = {"observation", "hypothesis", "plan", "risk", "confidence"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Missing fields: {missing}")

        plan = list(data["plan"])[: self._max_plan_steps] or ["Sin pasos."]
        try:
            confidence = max(0.0, min(1.0, float(data["confidence"])))
        except (TypeError, ValueError):
            confidence = 0.5

        return Monologue(
            input_summary=user_input[:500],
            observation=str(data["observation"])[:1000],
            hypothesis=str(data["hypothesis"])[:1000],
            plan=[str(p) for p in plan],
            risk=str(data.get("risk", "none"))[:500],
            confidence=confidence,
            backend="api",
        )


__all__ = ["APIFallbackBackend"]
