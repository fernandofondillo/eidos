"""API Key Providers — Fase 6.

Registro de providers soportados por la UI. Cada provider declara:
- id: identificador interno
- name: nombre para mostrar
- env_var: variable de entorno donde se guarda la key
- api_type: 'openai' | 'anthropic' | 'minimax' (protocolo)
- base_url: endpoint base
- default_model: modelo por defecto
- docs_url: link a docs para obtener API key

La UI usa este registro para renderizar el formulario de Settings.
El backend lo usa para cargar las keys desde .env y configurar el
APIFallbackBackend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiProvider:
    id: str
    name: str
    env_var: str
    api_type: str  # 'openai' | 'anthropic' | 'minimax'
    base_url: str
    default_model: str
    docs_url: str
    description: str = ""


# Catálogo de providers soportados.
# Cualquier API compatible con OpenAI (chat completions) puede añadirse
# aquí con api_type='openai'. Anthropic usa su propio protocolo.
# MiniMax ofrece dos vías: su API nativa (api_type='minimax') y vía
# endpoint compatible Anthropic (api_type='anthropic', base_url de minimax.io).
PROVIDERS: list[ApiProvider] = [
    ApiProvider(
        id="openai",
        name="OpenAI",
        env_var="OPENAI_API_KEY",
        api_type="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        docs_url="https://platform.openai.com/api-keys",
        description="GPT-4o, GPT-4, etc. Compatible con cualquier API OpenAI.",
    ),
    ApiProvider(
        id="anthropic",
        name="Anthropic Claude",
        env_var="ANTHROPIC_API_KEY",
        api_type="anthropic",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-5-sonnet-20241022",
        docs_url="https://console.anthropic.com/settings/keys",
        description="Claude 3.5 Sonnet, Opus, etc.",
    ),
    ApiProvider(
        id="minimax",
        name="MiniMax (API nativa)",
        env_var="MINIMAX_API_KEY",
        api_type="minimax",
        base_url="https://api.minimaxi.chat/v1",
        default_model="MiniMax-Text-01",
        docs_url="https://platform.minimaxi.com/user-center/basic-information/interface-search",
        description="MiniMax Text 01 vía API nativa. Buen razonamiento en español.",
    ),
    ApiProvider(
        id="minimax_anthropic",
        name="MiniMax-M3 (vía Anthropic)",
        env_var="MINIMAX_ANTHROPIC_API_KEY",
        api_type="anthropic",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
        docs_url="https://platform.minimaxi.com/user-center/basic-information/interface-search",
        description=(
            "MiniMax-M3 a través del endpoint compatible con Anthropic "
            "(api.minimax.io/anthropic). Usa el TOKEN plan de MiniMax con "
            "el protocolo de Claude. Solo necesitas tu API key de MiniMax."
        ),
    ),
    ApiProvider(
        id="openrouter",
        name="OpenRouter",
        env_var="OPENROUTER_API_KEY",
        api_type="openai",
        base_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-3.5-sonnet",
        docs_url="https://openrouter.ai/keys",
        description="Acceso a 100+ modelos vía una sola API. Compatible OpenAI.",
    ),
    ApiProvider(
        id="together",
        name="Together.ai",
        env_var="TOGETHER_API_KEY",
        api_type="openai",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        docs_url="https://api.together.ai/settings/api-keys",
        description="Llama, Mixtral y otros modelos open-source. Compatible OpenAI.",
    ),
    ApiProvider(
        id="groq",
        name="Groq",
        env_var="GROQ_API_KEY",
        api_type="openai",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        docs_url="https://console.groq.com/keys",
        description="Inferencia ultra-rápida de Llama. Compatible OpenAI.",
    ),
]


def get_provider(provider_id: str) -> ApiProvider | None:
    """Devuelve el provider por id, o None."""
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None


def list_providers() -> list[dict[str, Any]]:
    """Lista los providers para la UI."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "env_var": p.env_var,
            "api_type": p.api_type,
            "base_url": p.base_url,
            "default_model": p.default_model,
            "docs_url": p.docs_url,
            "description": p.description,
        }
        for p in PROVIDERS
    ]


__all__ = ["ApiProvider", "PROVIDERS", "get_provider", "list_providers"]
