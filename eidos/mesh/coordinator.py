"""MeshCoordinator — Fase 4 facade.

Une transport + bus + election + arbitrator en una sola API que el
resto del sistema (EidosCore, CortexHub) consume.

Roles:
- LEADER: arranca heartbeat, registra handlers RPC para acquire_token,
  release_token, list_nodes, delegate_inference. Mantiene registry.
- WORKER: se registra con HELLO al Leader, escucha heartbeats, pide
  tokens vía RPC cuando necesita el CortexHub.

La API pública es la misma sea Leader o Worker — el Coordinator decide
internamente.

Uso:
    coord = MeshCoordinator.from_config(config, db_path)
    coord.start()  # arranca server + election
    if coord.am_i_leader:
        # soy el Primario
        ...
    # Pedir recurso (funciona en ambos roles):
    token = coord.acquire_resource('cortex', ttl_sec=60)
    if token:
        try:
            # usar el recurso
            ...
        finally:
            coord.release_resource(token.token_id)
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidos.mesh.arbitrator import ResourceArbitrator, ResourceToken
from eidos.mesh.bus import MeshBus
from eidos.mesh.election import LeaderElection
from eidos.mesh.protocol import (
    MeshMessage,
    NodeRole,
    NodeStatus,
    PubTopic,
    RpcMethod,
    error,
    pub,
    request,
    response,
)
from eidos.mesh.transport import TransportError, socket_path_for
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class MeshCoordinator:
    """Facade del MESH. Coordina election + bus + arbitrator."""

    def __init__(
        self,
        node_id: str,
        db_path: Path,
        runtime_dir: Path,
        lockfile_path: Path,
        heartbeat_interval_sec: float = 2.0,
        leader_timeout_sec: float = 6.0,
    ) -> None:
        self._node_id = node_id
        self._db_path = db_path
        self._runtime_dir = runtime_dir
        self._lockfile = lockfile_path
        self._heartbeat_interval = heartbeat_interval_sec
        self._leader_timeout = leader_timeout_sec

        # Componentes
        self._bus = MeshBus(node_id=node_id, runtime_dir=runtime_dir)
        self._election = LeaderElection(
            node_id=node_id,
            lockfile_path=lockfile_path,
            bus=self._bus,
            heartbeat_interval_sec=heartbeat_interval_sec,
            leader_timeout_sec=leader_timeout_sec,
        )
        # El arbitrator se crea cuando soy Leader (en start)
        self._arbitrator: ResourceArbitrator | None = None

        # Registry de nodos (vivo solo en Leader)
        self._known_nodes: dict[str, dict[str, Any]] = {}

    # ---------------- Factory ----------------

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        db_path: Path,
        project_root: Path,
    ) -> "MeshCoordinator | None":
        """Construye el coordinator desde config. Devuelve None si mesh deshabilitado."""
        mesh_cfg = config.get("mesh", {})
        if not mesh_cfg.get("enabled", False):
            return None

        node_id = str(uuid.uuid4())
        runtime_dir = project_root / mesh_cfg.get("runtime_dir", "data/runtime")
        lockfile_path = Path(mesh_cfg.get("lockfile_path", "/tmp/eidos.mesh.leader"))
        heartbeat = float(mesh_cfg.get("heartbeat_sec", 2.0))
        leader_timeout = float(mesh_cfg.get("leader_timeout_sec", 6.0))

        return cls(
            node_id=node_id,
            db_path=db_path,
            runtime_dir=runtime_dir,
            lockfile_path=lockfile_path,
            heartbeat_interval_sec=heartbeat,
            leader_timeout_sec=leader_timeout,
        )

    # ---------------- Properties ----------------

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def role(self) -> NodeRole:
        return self._election.role

    @property
    def am_i_leader(self) -> bool:
        return self._election.am_i_leader

    @property
    def leader_id(self) -> str | None:
        return self._election.leader_id

    @property
    def bus(self) -> MeshBus:
        return self._bus

    @property
    def arbitrator(self) -> ResourceArbitrator | None:
        return self._arbitrator

    @property
    def socket_path(self) -> Path:
        return self._bus.socket_path

    # ---------------- Lifecycle ----------------

    def start(self) -> None:
        """Arranca el coordinator: server + election + heartbeat/watcher."""
        # 1. Arrancar bus (server local)
        self._bus.start()
        logger.info("mesh_coordinator_started", node_id=self._node_id, address=self._bus.address)

        # 2. Suscribirse a topics relevantes
        self._bus.subscribe(PubTopic.HEARTBEAT, self._on_heartbeat)
        self._bus.subscribe(PubTopic.NODE_JOINED, self._on_node_joined)
        self._bus.subscribe(PubTopic.NODE_LEFT, self._on_node_left)
        self._bus.subscribe(PubTopic.LEADER_ANNOUNCE, self._on_leader_announce)

        # 3. Intentar adquirir liderazgo
        role = self._election.try_acquire_leadership()
        if role is NodeRole.LEADER:
            self._become_leader()
        else:
            self._become_worker()

    def stop(self) -> None:
        """Detiene el coordinator limpiamente."""
        # Anunciar salida
        try:
            self._bus.publish(
                pub(
                    source=self._node_id,
                    topic=PubTopic.NODE_LEFT,
                    params={"node_id": self._node_id, "ts": _now_iso()},
                )
            )
        except Exception:
            pass
        # Si era Leader, liberar lockfile
        if self.am_i_leader:
            self._election.release_leadership()
        else:
            self._election.stop_watcher()
        self._bus.stop()
        logger.info("mesh_coordinator_stopped", node_id=self._node_id)

    # ---------------- Role transitions ----------------

    def _become_leader(self) -> None:
        """Transición a Leader: arranca heartbeat + arbitrator + handlers."""
        self._arbitrator = ResourceArbitrator(db_path=self._db_path, leader_node_id=self._node_id)
        self._election.start_heartbeat()
        # Registrar handlers RPC
        self._bus.register_request_handler(RpcMethod.HELLO, self._handle_hello)
        self._bus.register_request_handler(RpcMethod.GOODBYE, self._handle_goodbye)
        self._bus.register_request_handler(RpcMethod.ACQUIRE_TOKEN, self._handle_acquire_token)
        self._bus.register_request_handler(RpcMethod.RELEASE_TOKEN, self._handle_release_token)
        self._bus.register_request_handler(RpcMethod.LIST_NODES, self._handle_list_nodes)
        self._bus.register_request_handler(RpcMethod.WHO_IS_LEADER, self._handle_who_is_leader)
        # Registrar mi propio socket en el registry de peers (para que publish no falle)
        self._bus.register_peer(self._node_id, self._bus.socket_path)
        # Anunciar liderazgo
        self._bus.publish(
            pub(
                source=self._node_id,
                topic=PubTopic.LEADER_ANNOUNCE,
                params={
                    "leader_id": self._node_id,
                    "socket_path": str(self._bus.socket_path),
                    "ts": _now_iso(),
                },
            )
        )
        # Registrar mi nodo en DB
        self._register_node_in_db(self._node_id, NodeRole.LEADER, NodeStatus.ALIVE)
        logger.info("mesh_became_leader", node_id=self._node_id)

    def _become_worker(self) -> None:
        """Transición a Worker: arranca watcher y se registra con Leader."""
        self._election.start_watcher()
        # Registrar mi nodo en DB
        self._register_node_in_db(self._node_id, NodeRole.WORKER, NodeStatus.ALIVE)
        # Si conozco al Leader, mandar HELLO
        if self.leader_id and self.leader_id != self._node_id:
            # Aún no conozco el socket del Leader; el watcher lo resolverá
            # cuando llegue el primer heartbeat o leader_announce.
            pass
        logger.info("mesh_became_worker", node_id=self._node_id, leader=self.leader_id)

    # ---------------- Resource acquisition (cualquier rol) ----------------

    def acquire_resource(
        self,
        resource: str,
        ttl_sec: float = 30.0,
        metadata: dict[str, Any] | None = None,
    ) -> ResourceToken | None:
        """Pide un recurso al arbitrator. Si soy Leader, local; si Worker, RPC."""
        if self.am_i_leader:
            # Local directo
            assert self._arbitrator is not None
            return self._arbitrator.acquire(
                resource=resource,
                holder_node_id=self._node_id,
                ttl_sec=ttl_sec,
                metadata=metadata,
            )
        # Worker → RPC al Leader
        resp = self._bus.send_request_to_leader(
            method=RpcMethod.ACQUIRE_TOKEN,
            params={
                "resource": resource,
                "holder": self._node_id,
                "ttl_sec": ttl_sec,
                "metadata": metadata or {},
            },
            timeout=5.0,
        )
        if resp.error or resp.params is None:
            logger.warning("mesh_acquire_rpc_failed", error=resp.error)
            return None
        params = resp.params
        if not params.get("granted", False):
            return None
        return ResourceToken(
            token_id=params["token_id"],
            resource=resource,
            holder_node_id=self._node_id,
            acquired_at=params["acquired_at"],
            expires_at=params["expires_at"],
            released_at=None,
            metadata=params.get("metadata", {}),
        )

    def release_resource(self, token_id: str) -> bool:
        """Libera un token. Si soy Leader, local; si Worker, RPC."""
        if self.am_i_leader:
            assert self._arbitrator is not None
            return self._arbitrator.release(token_id)
        resp = self._bus.send_request_to_leader(
            method=RpcMethod.RELEASE_TOKEN,
            params={"token_id": token_id, "holder": self._node_id},
            timeout=5.0,
        )
        return resp.params is not None and resp.params.get("released", False)

    # ---------------- RPC handlers (solo Leader) ----------------

    def _handle_hello(self, msg: MeshMessage) -> MeshMessage:
        """Worker se registra."""
        params = msg.params or {}
        worker_id = params.get("node_id", msg.source)
        worker_socket = params.get("socket_path")
        if worker_socket:
            self._bus.register_peer(worker_id, Path(worker_socket))
        self._known_nodes[worker_id] = {
            "socket_path": worker_socket,
            "pid": params.get("pid"),
            "hostname": params.get("hostname"),
            "joined_at": _now_iso(),
        }
        self._register_node_in_db(worker_id, NodeRole.WORKER, NodeStatus.ALIVE)
        logger.info("mesh_worker_joined", worker_id=worker_id)
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={
                "acknowledged": True,
                "leader_id": self._node_id,
                "leader_socket": str(self._bus.socket_path),
            },
            target=msg.source,
        )

    def _handle_goodbye(self, msg: MeshMessage) -> MeshMessage:
        params = msg.params or {}
        worker_id = params.get("node_id", msg.source)
        self._bus.unregister_peer(worker_id)
        self._known_nodes.pop(worker_id, None)
        # Liberar tokens del worker que se va
        if self._arbitrator is not None:
            self._arbitrator.release_all_for_holder(worker_id)
        self._update_node_status_in_db(worker_id, NodeStatus.LEAVING)
        logger.info("mesh_worker_left", worker_id=worker_id)
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={"acknowledged": True},
            target=msg.source,
        )

    def _handle_acquire_token(self, msg: MeshMessage) -> MeshMessage:
        params = msg.params or {}
        resource = params.get("resource")
        holder = params.get("holder", msg.source)
        ttl_sec = float(params.get("ttl_sec", 30.0))
        metadata = params.get("metadata", {})

        if not resource or self._arbitrator is None:
            return error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg="Invalid request or not leader",
                target=msg.source,
            )

        token = self._arbitrator.acquire(
            resource=resource,
            holder_node_id=holder,
            ttl_sec=ttl_sec,
            metadata=metadata,
        )
        if token is None:
            return response(
                source=self._node_id,
                in_reply_to=msg.id,
                params={"granted": False, "reason": "resource busy"},
                target=msg.source,
            )
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={
                "granted": True,
                "token_id": token.token_id,
                "acquired_at": token.acquired_at,
                "expires_at": token.expires_at,
                "metadata": token.metadata,
            },
            target=msg.source,
        )

    def _handle_release_token(self, msg: MeshMessage) -> MeshMessage:
        params = msg.params or {}
        token_id = params.get("token_id")
        if not token_id or self._arbitrator is None:
            return error(
                source=self._node_id,
                in_reply_to=msg.id,
                error_msg="Missing token_id or not leader",
                target=msg.source,
            )
        released = self._arbitrator.release(token_id)
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={"released": released},
            target=msg.source,
        )

    def _handle_list_nodes(self, msg: MeshMessage) -> MeshMessage:
        # Incluir el Leader en la lista
        nodes = [
            {
                "node_id": self._node_id,
                "role": NodeRole.LEADER.value,
                "socket_path": str(self._bus.socket_path),
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
            }
        ]
        for nid, info in self._known_nodes.items():
            nodes.append({
                "node_id": nid,
                "role": NodeRole.WORKER.value,
                "socket_path": info.get("socket_path"),
                "pid": info.get("pid"),
                "hostname": info.get("hostname"),
            })
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={"nodes": nodes, "leader_id": self._node_id},
            target=msg.source,
        )

    def _handle_who_is_leader(self, msg: MeshMessage) -> MeshMessage:
        return response(
            source=self._node_id,
            in_reply_to=msg.id,
            params={
                "leader_id": self._node_id,
                "socket_path": str(self._bus.socket_path),
            },
            target=msg.source,
        )

    # ---------------- Pub/Sub callbacks ----------------

    def _on_heartbeat(self, msg: MeshMessage) -> None:
        # Actualizar vista del Leader
        self._election.on_heartbeat(msg)
        # Si el heartbeat viene con socket_path del Leader, registrarlo
        if msg.params and msg.params.get("leader_id"):
            # Ya tenemos el Leader; su socket lo averiguamos por otros medios
            pass

    def _on_node_joined(self, msg: MeshMessage) -> None:
        params = msg.params or {}
        new_node = params.get("node_id")
        if new_node and new_node != self._node_id:
            logger.info("mesh_node_joined_broadcast", node_id=new_node)

    def _on_node_left(self, msg: MeshMessage) -> None:
        params = msg.params or {}
        gone_node = params.get("node_id")
        if gone_node:
            self._bus.unregister_peer(gone_node)
            self._known_nodes.pop(gone_node, None)
            if self.am_i_leader and self._arbitrator is not None:
                self._arbitrator.release_all_for_holder(gone_node)
            logger.info("mesh_node_left_broadcast", node_id=gone_node)

    def _on_leader_announce(self, msg: MeshMessage) -> None:
        params = msg.params or {}
        leader_id = params.get("leader_id")
        leader_socket = params.get("socket_path")
        if leader_id and leader_socket:
            self._bus.set_leader_socket(Path(leader_socket))
            self._bus.register_peer(leader_id, Path(leader_socket))
            # Si soy Worker, mandar HELLO al Leader
            if not self.am_i_leader and leader_id != self._node_id:
                self._send_hello(leader_id, Path(leader_socket))

    # ---------------- Worker registration ----------------

    def _send_hello(self, leader_id: str, leader_socket: Path) -> None:
        """Worker → Leader: registrarse."""
        msg = request(
            source=self._node_id,
            method=RpcMethod.HELLO,
            target=leader_id,
            params={
                "node_id": self._node_id,
                "socket_path": str(self._bus.socket_path),
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "ts": _now_iso(),
            },
        )
        try:
            from eidos.mesh.transport import MeshClient

            resp = MeshClient.send_request(leader_socket, msg, timeout=5.0)
            if resp.error:
                logger.warning("mesh_hello_failed", error=resp.error)
            else:
                logger.info("mesh_hello_acknowledged", leader=leader_id)
                # Si el Leader me dio su socket, registrarlo
                if resp.params and resp.params.get("leader_socket"):
                    self._bus.set_leader_socket(Path(resp.params["leader_socket"]))
        except TransportError as e:
            logger.warning("mesh_hello_transport_error", error=str(e))

    # ---------------- DB helpers ----------------

    def _register_node_in_db(
        self, node_id: str, role: NodeRole, status: NodeStatus
    ) -> None:
        import json
        import sqlite3

        now = _now_iso()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT INTO mesh_nodes(id, pid, hostname, socket_path, role, status,
                                       last_heartbeat, started_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role=excluded.role,
                    status=excluded.status,
                    last_heartbeat=excluded.last_heartbeat
                """,
                (
                    node_id,
                    os.getpid(),
                    socket.gethostname(),
                    str(self._bus.socket_path),
                    role.value,
                    status.value,
                    now,
                    now,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_node_status_in_db(self, node_id: str, status: NodeStatus) -> None:
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "UPDATE mesh_nodes SET status = ?, last_heartbeat = ? WHERE id = ?",
                (status.value, _now_iso(), node_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ---------------- Stats ----------------

    def stats(self) -> dict[str, Any]:
        s = {
            "module": "mesh_coordinator",
            "node_id": self._node_id,
            "role": self.role.value,
            "leader_id": self.leader_id,
            "am_i_leader": self.am_i_leader,
            "socket": str(self._bus.socket_path),
            "peers": len(self._bus.list_peers()),
        }
        if self._arbitrator is not None:
            s["arbitrator"] = self._arbitrator.stats()
        return s


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = ["MeshCoordinator"]
