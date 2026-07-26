"""Protocolo del MESH — Fase 4.

JSON-RPC 2.0 ligero sobre sockets UNIX. Mensajes tipados para:
- pub/sub: heartbeat, MEMORY_UPDATE, NODE_JOINED, NODE_LEFT.
- request/response: HELLO, ACQUIRE_TOKEN, RELEASE_TOKEN, LIST_NODES,
  DELEGATE_INFERENCE.

Todos los mensajes tienen id (UUID) y ts (ISO-8601 UTC).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Roles y estados
# ---------------------------------------------------------------------------


class NodeRole(str, Enum):
    LEADER = "leader"
    WORKER = "worker"
    CANDIDATE = "candidate"


class NodeStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    LEAVING = "leaving"


class MessageType(str, Enum):
    """Tipo de mensaje JSON-RPC."""

    PUB = "pub"
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"


class PubTopic(str, Enum):
    """Topics del bus pub/sub."""

    HEARTBEAT = "heartbeat"
    MEMORY_UPDATE = "memory_update"
    NODE_JOINED = "node_joined"
    NODE_LEFT = "node_left"
    LEADER_ANNOUNCE = "leader_announce"


# ---------------------------------------------------------------------------
# Mensaje base — JSON-RPC 2.0 adaptado
# ---------------------------------------------------------------------------


class MeshMessage(BaseModel):
    """Mensaje base del MESH. Todos los mensajes cumplen este schema."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    type: MessageType
    source: str  # node_id del emisor
    target: str | None = None  # node_id del destinatario (None = broadcast)
    topic: str | None = None  # solo para PUB
    method: str | None = None  # solo para REQUEST/RESPONSE
    params: dict[str, Any] | None = None
    in_reply_to: str | None = None  # para RESPONSE: id del REQUEST original
    error: str | None = None  # para ERROR

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> "MeshMessage":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Methods para REQUEST/RESPONSE
# ---------------------------------------------------------------------------


class RpcMethod(str, Enum):
    HELLO = "hello"
    ACQUIRE_TOKEN = "acquire_token"
    RELEASE_TOKEN = "release_token"
    LIST_NODES = "list_nodes"
    DELEGATE_INFERENCE = "delegate_inference"
    WHO_IS_LEADER = "who_is_leader"
    GOODBYE = "goodbye"


# ---------------------------------------------------------------------------
# Helpers para construir mensajes
# ---------------------------------------------------------------------------


def pub(
    source: str,
    topic: PubTopic | str,
    params: dict[str, Any] | None = None,
) -> MeshMessage:
    return MeshMessage(
        type=MessageType.PUB,
        source=source,
        topic=topic.value if isinstance(topic, PubTopic) else topic,
        params=params,
    )


def request(
    source: str,
    method: RpcMethod | str,
    params: dict[str, Any] | None = None,
    target: str | None = None,
) -> MeshMessage:
    return MeshMessage(
        type=MessageType.REQUEST,
        source=source,
        target=target,
        method=method.value if isinstance(method, RpcMethod) else method,
        params=params,
    )


def response(
    source: str,
    in_reply_to: str,
    params: dict[str, Any] | None = None,
    target: str | None = None,
) -> MeshMessage:
    return MeshMessage(
        type=MessageType.RESPONSE,
        source=source,
        target=target,
        in_reply_to=in_reply_to,
        params=params,
    )


def error(
    source: str,
    in_reply_to: str,
    error_msg: str,
    target: str | None = None,
) -> MeshMessage:
    return MeshMessage(
        type=MessageType.ERROR,
        source=source,
        target=target,
        in_reply_to=in_reply_to,
        error=error_msg,
    )


__all__ = [
    "NodeRole",
    "NodeStatus",
    "MessageType",
    "PubTopic",
    "RpcMethod",
    "MeshMessage",
    "pub",
    "request",
    "response",
    "error",
]
