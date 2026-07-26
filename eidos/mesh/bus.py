"""MeshBus — Fase 4.

Bus de mensajes local. Combina:
- pub/sub: el Leader publica heartbeat, MEMORY_UPDATE, etc. Workers se
  suscriben a topics.
- request/response: Workers envían requests al Leader (acquire_token,
  delegate_inference) y reciben responses.

Implementación v1:
- Cada instancia EIDOS tiene un MeshServer (escucha en su socket UNIX).
- El MeshBus mantiene un registry de peer sockets (workers → leader).
- publish() envía el mensaje a todos los peers conocidos (broadcast)
  o solo al Leader si el mensaje es un request con target=None.
- subscribe(topic, callback) registra callbacks locales para pub/sub.

Para tests, se puede inyectar un transport mock.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Protocol

from eidos.mesh.protocol import (
    MeshMessage,
    MessageType,
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
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Transport protocol — para inyectar mocks en tests
# ---------------------------------------------------------------------------


class TransportLike(Protocol):
    """Contrato que cualquier transporte debe cumplir."""

    def send_message(self, socket_path: Path, msg: MeshMessage, timeout: float = ...) -> None: ...

    def send_request(
        self, socket_path: Path, msg: MeshMessage, timeout: float = ...
    ) -> MeshMessage: ...


# ---------------------------------------------------------------------------
# MeshBus
# ---------------------------------------------------------------------------


class MeshBus:
    """Bus de mensajes del MESH. Fachada sobre MeshServer + MeshClient."""

    def __init__(
        self,
        node_id: str,
        runtime_dir: Path,
        transport: TransportLike | None = None,
    ) -> None:
        self._node_id = node_id
        self._runtime_dir = runtime_dir
        self._socket_path = socket_path_for(node_id, runtime_dir)
        self._transport = transport or _DefaultTransport()
        self._server: MeshServer | None = None
        self._subscribers: dict[str, list[Callable[[MeshMessage], None]]] = defaultdict(list)
        self._request_handlers: dict[str, Callable[[MeshMessage], MeshMessage]] = {}
        self._lock = threading.RLock()
        # Registry de peers conocidos: node_id → socket_path
        self._peers: dict[str, Path] = {}
        self._leader_socket: Path | None = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def address(self) -> str:
        return f"unix://{self._socket_path}"

    # ---------------- Lifecycle ----------------

    def start(self) -> None:
        """Arranca el servidor local que escucha mensajes entrantes."""
        self._server = MeshServer(
            socket_path=self._socket_path,
            handler=self._on_incoming,
        )
        self._server.start()

    def stop(self, timeout: float = 2.0) -> None:
        if self._server is not None:
            self._server.stop(timeout=timeout)
            self._server = None

    # ---------------- Peer registry ----------------

    def register_peer(self, peer_node_id: str, peer_socket_path: Path) -> None:
        with self._lock:
            self._peers[peer_node_id] = peer_socket_path

    def unregister_peer(self, peer_node_id: str) -> None:
        with self._lock:
            self._peers.pop(peer_node_id, None)

    def set_leader_socket(self, socket_path: Path | None) -> None:
        with self._lock:
            self._leader_socket = socket_path

    def get_peer_socket(self, node_id: str) -> Path | None:
        with self._lock:
            return self._peers.get(node_id)

    def get_leader_socket(self) -> Path | None:
        with self._lock:
            return self._leader_socket

    def list_peers(self) -> dict[str, Path]:
        with self._lock:
            return dict(self._peers)

    # ---------------- Pub/Sub ----------------

    def subscribe(self, topic: PubTopic | str, callback: Callable[[MeshMessage], None]) -> None:
        topic_str = topic.value if isinstance(topic, PubTopic) else topic
        with self._lock:
            self._subscribers[topic_str].append(callback)

    def publish(self, msg: MeshMessage) -> None:
        """Publica un mensaje a todos los peers conocidos (broadcast).

        También entrega a suscriptores locales (útil para tests y para
        que el propio nodo pueda escuchar sus propios eventos).
        """
        # 1. Entrega local (suscriptores del propio nodo)
        self._dispatch_pub(msg)
        # 2. Entrega a peers remotos
        peers = self.list_peers()
        for peer_id, peer_socket in peers.items():
            # No enviarme a mí mismo vía socket (ya se entregó local)
            if peer_id == self._node_id:
                continue
            try:
                self._transport.send_message(peer_socket, msg, timeout=2.0)
            except TransportError as e:
                logger.warning(
                    "mesh_publish_peer_failed",
                    peer=peer_id,
                    error=str(e),
                )

    # ---------------- Request / Response ----------------

    def register_request_handler(
        self,
        method: RpcMethod | str,
        handler: Callable[[MeshMessage], MeshMessage],
    ) -> None:
        method_str = method.value if isinstance(method, RpcMethod) else method
        with self._lock:
            self._request_handlers[method_str] = handler

    def send_request(
        self,
        target_node_id: str,
        method: RpcMethod | str,
        params: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> MeshMessage:
        """Envía un request a un peer y espera su response."""
        peer_socket = self.get_peer_socket(target_node_id)
        if peer_socket is None:
            return error(
                source=self._node_id,
                in_reply_to="",
                error_msg=f"Unknown peer: {target_node_id}",
            )
        msg = request(
            source=self._node_id,
            method=method,
            params=params,
            target=target_node_id,
        )
        try:
            return self._transport.send_request(peer_socket, msg, timeout=timeout)
        except (TransportError, TransportTimeout) as e:
            return error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg=str(e),
            )

    def send_request_to_leader(
        self,
        method: RpcMethod | str,
        params: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> MeshMessage:
        """Conveniencia: envía request al Leader (socket conocido)."""
        leader_socket = self.get_leader_socket()
        if leader_socket is None:
            return error(
                source=self._node_id,
                in_reply_to="",
                error_msg="No leader known",
            )
        msg = request(
            source=self._node_id,
            method=method,
            params=params,
            target=None,  # Leader
        )
        try:
            return self._transport.send_request(leader_socket, msg, timeout=timeout)
        except (TransportError, TransportTimeout) as e:
            return error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg=str(e),
            )

    # ---------------- Incoming message dispatch ----------------

    def _on_incoming(self, msg: MeshMessage, conn: Any) -> None:
        """Manejador principal: dispatcha según tipo de mensaje."""
        try:
            if msg.type == MessageType.PUB:
                self._dispatch_pub(msg)
            elif msg.type == MessageType.REQUEST:
                self._dispatch_request(msg, conn)
            elif msg.type == MessageType.RESPONSE:
                # Las responses se manejan en send_request (sync). Si llegan
                # aquí es porque llegaron tarde; las ignoramos.
                logger.debug("mesh_late_response_ignored", msg_id=msg.id)
            elif msg.type == MessageType.ERROR:
                logger.warning("mesh_error_received", error=msg.error, msg_id=msg.id)
        except Exception as e:
            logger.error("mesh_dispatch_failed", error=str(e), msg_id=msg.id)

    def _dispatch_pub(self, msg: MeshMessage) -> None:
        if msg.topic is None:
            return
        with self._lock:
            callbacks = list(self._subscribers.get(msg.topic, []))
        for cb in callbacks:
            try:
                cb(msg)
            except Exception as e:
                logger.warning("mesh_subscriber_callback_failed", error=str(e))

    def _dispatch_request(self, msg: MeshMessage, conn: Any) -> None:
        if msg.method is None:
            return
        with self._lock:
            handler = self._request_handlers.get(msg.method)
        if handler is None:
            # Sin handler → responder error
            err = error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg=f"No handler for method: {msg.method}",
                target=msg.source,
            )
            try:
                conn.sendall((err.to_json() + "\n").encode("utf-8"))
            except OSError:
                pass
            return
        try:
            resp = handler(msg)
            # Asegurar que el target apunta al solicitante
            if resp.target is None:
                resp = resp.model_copy(update={"target": msg.source})
            conn.sendall((resp.to_json() + "\n").encode("utf-8"))
        except Exception as e:
            err = error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg=f"Handler error: {e}",
                target=msg.source,
            )
            try:
                conn.sendall((err.to_json() + "\n").encode("utf-8"))
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Default transport (usa MeshClient real)
# ---------------------------------------------------------------------------


class _DefaultTransport:
    """Implementación por defecto del transporte, usando sockets UNIX."""

    def send_message(self, socket_path: Path, msg: MeshMessage, timeout: float = 5.0) -> None:
        MeshClient.send_message(socket_path, msg, timeout=timeout)

    def send_request(
        self, socket_path: Path, msg: MeshMessage, timeout: float = 10.0
    ) -> MeshMessage:
        return MeshClient.send_request(socket_path, msg, timeout=timeout)


__all__ = ["MeshBus", "TransportLike"]
