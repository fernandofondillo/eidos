"""EIDOS MESH — enjambre y cooperación (Fase 4).

Componentes:
- protocol:     mensajes JSON-RPC 2.0 tipados.
- transport:    sockets UNIX (POSIX) — server y cliente.
- election:     LeaderElection (lockfile atómico + heartbeat anti split-brain).
- bus:          MeshBus — pub/sub + request/response.
- arbitrator:   ResourceArbitrator — tokens con TTL anti-deadlock.
- coordinator:  MeshCoordinator — facade unificada.
"""

from eidos.mesh.arbitrator import ResourceArbitrator, ResourceToken
from eidos.mesh.bus import MeshBus
from eidos.mesh.coordinator import MeshCoordinator
from eidos.mesh.election import LeaderElection
from eidos.mesh.protocol import (
    MeshMessage,
    MessageType,
    NodeRole,
    NodeStatus,
    PubTopic,
    RpcMethod,
    error,
    pub,
    request,
    response,
)
from eidos.mesh.transport import (
    MeshClient,
    MeshServer,
    TransportError,
    TransportTimeout,
    socket_path_for,
)

__all__ = [
    "MeshCoordinator",
    "MeshBus",
    "MeshServer",
    "MeshClient",
    "LeaderElection",
    "ResourceArbitrator",
    "ResourceToken",
    "MeshMessage",
    "MessageType",
    "NodeRole",
    "NodeStatus",
    "PubTopic",
    "RpcMethod",
    "TransportError",
    "TransportTimeout",
    "socket_path_for",
    "pub",
    "request",
    "response",
    "error",
]
