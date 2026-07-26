"""Leader Election — Fase 4.

Dos mecanismos combinados (anti split-brain):

1. Lockfile atómico: O_CREAT|O_EXCL sobre /tmp/eidos.mesh.leader.
   - Gana quien lo adquiere (operación atómica del SO).
   - Contiene PID + hostname + node_id para diagnóstico.
   - Si el proceso muere, el SO libera el fd pero el archivo queda;
     el heartbeat sirve para detectar leader muerto.

2. Heartbeat vía bus pub/sub: el Leader publica `heartbeat` cada 2s.
   - Si ningún heartbeat en `leader_timeout_sec` (default 6s) → re-elección.
   - Workers y Candidates escuchan y actualizan su vista del Leader.

API:
    election = LeaderElection(node_id, lockfile_path, bus)
    role = election.try_acquire_leadership()
    election.start_heartbeat()  # si soy Leader
    election.stop_heartbeat()
    election.release_leadership()
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidos.mesh.bus import MeshBus
from eidos.mesh.protocol import NodeRole, PubTopic, pub
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class LeaderElection:
    """Elección de Leader con lockfile atómico + heartbeat."""

    def __init__(
        self,
        node_id: str,
        lockfile_path: Path,
        bus: MeshBus,
        heartbeat_interval_sec: float = 2.0,
        leader_timeout_sec: float = 6.0,
    ) -> None:
        self._node_id = node_id
        self._lockfile = lockfile_path
        self._bus = bus
        self._heartbeat_interval = max(0.5, float(heartbeat_interval_sec))
        self._leader_timeout = max(2.0, float(leader_timeout_sec))
        self._role: NodeRole = NodeRole.WORKER
        self._leader_id: str | None = None
        self._leader_pid: int | None = None
        self._last_heartbeat_seen: float = 0.0
        self._heartbeat_thread: threading.Thread | None = None
        self._watcher_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    @property
    def role(self) -> NodeRole:
        with self._lock:
            return self._role

    @property
    def leader_id(self) -> str | None:
        with self._lock:
            return self._leader_id

    @property
    def am_i_leader(self) -> bool:
        return self.role is NodeRole.LEADER

    # ---------------- Adquirir / liberar liderazgo ----------------

    def try_acquire_leadership(self) -> NodeRole:
        """Intenta adquirir el lockfile atómico. Si gana, soy Leader."""
        try:
            # O_CREAT|O_EXCL: atómico en POSIX. Falla si el archivo ya existe.
            fd = os.open(
                str(self._lockfile),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            payload = {
                "node_id": self._node_id,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "acquired_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            }
            os.write(fd, (json.dumps(payload) + "\n").encode("utf-8"))
            os.close(fd)
            with self._lock:
                self._role = NodeRole.LEADER
                self._leader_id = self._node_id
            logger.info("mesh_leadership_acquired", node_id=self._node_id)
            return NodeRole.LEADER
        except FileExistsError:
            # Alguien más es Leader. Leer quién.
            self._read_existing_leader()
            with self._lock:
                self._role = NodeRole.WORKER
            logger.info(
                "mesh_leadership_denied_existing",
                leader_id=self._leader_id,
            )
            return NodeRole.WORKER
        except OSError as e:
            logger.error("mesh_leadership_acquire_failed", error=str(e))
            with self._lock:
                self._role = NodeRole.WORKER
            return NodeRole.WORKER

    def _read_existing_leader(self) -> None:
        """Lee el lockfile para saber quién es el Leader actual."""
        try:
            data = json.loads(self._lockfile.read_text(encoding="utf-8").strip())
            with self._lock:
                self._leader_id = data.get("node_id")
                self._leader_pid = data.get("pid")
        except (OSError, ValueError):
            # Lockfile corrupto o ilegible — no sabemos quién es Leader
            with self._lock:
                self._leader_id = None
                self._leader_pid = None

    def release_leadership(self) -> None:
        """Libera el liderazgo. Solo el Leader debe llamarlo."""
        self.stop_heartbeat()
        try:
            if self._lockfile.exists():
                self._lockfile.unlink()
        except OSError as e:
            logger.warning("mesh_release_lockfile_failed", error=str(e))
        with self._lock:
            self._role = NodeRole.WORKER
            self._leader_id = None
        logger.info("mesh_leadership_released")

    # ---------------- Heartbeat (Leader) ----------------

    def start_heartbeat(self) -> None:
        """Arranca el hilo que publica heartbeat cada N segundos."""
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return
        self._stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="mesh-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.info("mesh_heartbeat_started", interval=self._heartbeat_interval)

    def stop_heartbeat(self) -> None:
        if self._heartbeat_thread is None:
            return
        self._stop.set()
        self._heartbeat_thread.join(timeout=2.0)
        self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set() and self.am_i_leader:
            try:
                msg = pub(
                    source=self._node_id,
                    topic=PubTopic.HEARTBEAT,
                    params={
                        "leader_id": self._node_id,
                        "pid": os.getpid(),
                        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    },
                )
                self._bus.publish(msg)
                with self._lock:
                    self._last_heartbeat_seen = time.time()
            except Exception as e:
                logger.warning("mesh_heartbeat_publish_failed", error=str(e))
            if self._stop.wait(self._heartbeat_interval):
                break

    # ---------------- Watcher (Workers) ----------------

    def start_watcher(self) -> None:
        """Arranca el hilo que vigila heartbeats del Leader."""
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            return
        self._stop.clear()
        self._watcher_thread = threading.Thread(
            target=self._watcher_loop,
            name="mesh-watcher",
            daemon=True,
        )
        self._watcher_thread.start()

    def stop_watcher(self) -> None:
        if self._watcher_thread is None:
            return
        self._stop.set()
        self._watcher_thread.join(timeout=2.0)
        self._watcher_thread = None

    def _watcher_loop(self) -> None:
        """Vigila que el Leader sigue enviando heartbeats. Si timeout,
        intenta re-elección."""
        while not self._stop.is_set():
            if self._leader_id is None:
                # No sé quién es el Leader; intentar elección
                self._try_reelection()
            elif time.time() - self._last_heartbeat_seen > self._leader_timeout:
                logger.warning(
                    "mesh_leader_timeout",
                    leader_id=self._leader_id,
                    timeout=self._leader_timeout,
                )
                self._try_reelection()
            if self._stop.wait(self._heartbeat_interval):
                break

    def _try_reelection(self) -> None:
        """Si el Leader parece muerto, intentar adquirir el liderazgo."""
        # Borrar lockfile stale si el PID ya no existe
        if self._leader_pid is not None and not _pid_alive(self._leader_pid):
            try:
                if self._lockfile.exists():
                    self._lockfile.unlink()
                    logger.info("mesh_stale_lockfile_removed", pid=self._leader_pid)
            except OSError:
                pass
        role = self.try_acquire_leadership()
        if role is NodeRole.LEADER:
            self.start_heartbeat()

    def on_heartbeat(self, msg: Any) -> None:
        """Callback para recibir heartbeats del bus."""
        if msg.params is None:
            return
        leader_id = msg.params.get("leader_id")
        if leader_id is None:
            return
        with self._lock:
            self._leader_id = leader_id
            self._leader_pid = msg.params.get("pid")
            self._last_heartbeat_seen = time.time()


def _pid_alive(pid: int) -> bool:
    """Verifica si un PID está vivo. POSIX: kill(pid, 0)."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


__all__ = ["LeaderElection"]
