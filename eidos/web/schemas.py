"""Schemas Pydantic para la API web — Fase 5.

Estos modelos definen el contrato entre el frontend React y el backend
Python. Cualquier cambio aquí debe reflejarse en el frontend.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Petición de chat del usuario."""

    message: str = Field(..., min_length=1, max_length=5000)
    context: str | None = None


class ForgeRequest(BaseModel):
    """Petición de forja de cápsula."""

    request: str = Field(..., min_length=3, max_length=500)
    force_pending: bool = False


class ApproveRequest(BaseModel):
    """Aprobación de draft."""

    draft_id: str


class ConfigUpdate(BaseModel):
    """Actualización parcial de config."""

    config: dict[str, Any]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Respuesta completa de un turno de chat."""

    text: str
    monologue_id: str
    route_type: str
    confidence: float
    reward_delta: float
    monologue_backend: str
    memory_context: list[dict[str, Any]] | None = None
    evolution_event: dict[str, Any] | None = None
    # El monologue completo para visualización
    monologue: dict[str, Any] | None = None


class StatsResponse(BaseModel):
    """Estadísticas de las 5 capas de memoria."""

    sensory: dict[str, Any]
    episodic: dict[str, Any]
    semantic: dict[str, Any]
    procedural: dict[str, Any]
    metacognitive: dict[str, Any]


class CapsulesResponse(BaseModel):
    """Lista de cápsulas y drafts."""

    drafts: list[dict[str, Any]]
    active: list[dict[str, Any]]


class MeshStatusResponse(BaseModel):
    """Estado del enjambre MESH."""

    enabled: bool
    node_id: str | None = None
    role: str | None = None
    leader_id: str | None = None
    socket: str | None = None
    peers: int = 0
    arbitrator: dict[str, Any] | None = None


class MotivationResponse(BaseModel):
    """Estadísticas de reward signal."""

    session_total_reward: float
    by_driver: dict[str, dict[str, float]]
    confidence_window_size: int
    satisfaction_streak: int
    satisfaction_window: int
    recent_rewards: list[dict[str, Any]]


class EvolutionResponse(BaseModel):
    """Estadísticas del EvolutionLoop."""

    auto_forge_enabled: bool
    total_capsules: int
    favorites: int
    promotion_candidates: int
    promotion_threshold: int
    promotion_window_hours: int


class HealthResponse(BaseModel):
    """Health check."""

    status: str = "ok"
    version: str
    backend: str
    mesh_enabled: bool


# ---------------------------------------------------------------------------
# WebSocket message schemas
# ---------------------------------------------------------------------------


class WSIncoming(BaseModel):
    """Mensaje entrante del WebSocket."""

    type: str  # 'chat' | 'ping'
    message: str | None = None
    context: str | None = None


class WSOutgoing(BaseModel):
    """Mensaje saliente del WebSocket."""

    type: str  # 'monologue' | 'response' | 'error' | 'pong'
    data: dict[str, Any] | None = None
    error: str | None = None


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ForgeRequest",
    "ApproveRequest",
    "ConfigUpdate",
    "StatsResponse",
    "CapsulesResponse",
    "MeshStatusResponse",
    "MotivationResponse",
    "EvolutionResponse",
    "HealthResponse",
    "WSIncoming",
    "WSOutgoing",
]
