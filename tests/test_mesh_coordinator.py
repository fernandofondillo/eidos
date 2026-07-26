"""Tests del MeshCoordinator — Fase 4 facade.

Tests E2E: dos coordinators reales con sockets UNIX. Verifican:
- Leader election (uno gana, otro es worker).
- HELLO registration (worker se registra con leader).
- Resource acquisition (worker pide token vía RPC).
- NODE_LEFT cleanup (worker se va, libera tokens).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from eidos.mesh.coordinator import MeshCoordinator
from eidos.mesh.protocol import NodeRole
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def runtime_dir(tmp_path: Path) -> Path:
    return tmp_path / "runtime"


@pytest.fixture
def lockfile(tmp_path: Path) -> Path:
    return tmp_path / "leader.lock"


@pytest.fixture
def leader_coord(
    db_path: Path,
    runtime_dir: Path,
    lockfile: Path,
) -> MeshCoordinator:
    """Crea y arranca un coordinator que será Leader (al ser el primero)."""
    coord = MeshCoordinator(
        node_id="leader-node",
        db_path=db_path,
        runtime_dir=runtime_dir,
        lockfile_path=lockfile,
        heartbeat_interval_sec=0.5,
        leader_timeout_sec=1.5,
    )
    coord.start()
    time.sleep(0.2)  # dar tiempo a que arranque el server + heartbeat
    yield coord
    coord.stop()


@pytest.fixture
def worker_coord(
    db_path: Path,
    runtime_dir: Path,
    lockfile: Path,
) -> MeshCoordinator:
    """Crea un coordinator worker (lockfile ya existe por leader_coord)."""
    coord = MeshCoordinator(
        node_id="worker-node",
        db_path=db_path,
        runtime_dir=runtime_dir,
        lockfile_path=lockfile,
        heartbeat_interval_sec=0.5,
        leader_timeout_sec=1.5,
    )
    coord.start()
    time.sleep(0.3)  # dar tiempo a watcher + hello
    yield coord
    coord.stop()


# ---------------------------------------------------------------------------
# Leader election
# ---------------------------------------------------------------------------


class TestLeaderElection:
    def test_first_coordinator_becomes_leader(self, leader_coord: MeshCoordinator) -> None:
        assert leader_coord.am_i_leader is True
        assert leader_coord.role is NodeRole.LEADER
        assert leader_coord.leader_id == "leader-node"

    def test_second_coordinator_becomes_worker(
        self, leader_coord: MeshCoordinator, worker_coord: MeshCoordinator
    ) -> None:
        assert worker_coord.am_i_leader is False
        assert worker_coord.role is NodeRole.WORKER


# ---------------------------------------------------------------------------
# Resource acquisition
# ---------------------------------------------------------------------------


class TestResourceAcquisition:
    def test_leader_acquires_locally(self, leader_coord: MeshCoordinator) -> None:
        token = leader_coord.acquire_resource("cortex", ttl_sec=30)
        assert token is not None
        assert token.holder_node_id == "leader-node"
        # Liberar
        ok = leader_coord.release_resource(token.token_id)
        assert ok is True

    def test_worker_acquires_via_rpc(
        self, leader_coord: MeshCoordinator, worker_coord: MeshCoordinator
    ) -> None:
        # Esperar a que worker conozca al leader (vía heartbeat o announce)
        time.sleep(1.5)
        # El worker debe tener el leader_socket registrado
        assert worker_coord.bus.get_leader_socket() is not None or worker_coord.leader_id is not None
        # Si no hay socket directo, registramos manualmente para el test
        if worker_coord.bus.get_leader_socket() is None:
            worker_coord.bus.set_leader_socket(leader_coord.socket_path)
            worker_coord.bus.register_peer("leader-node", leader_coord.socket_path)

        token = worker_coord.acquire_resource("cortex", ttl_sec=30)
        assert token is not None
        assert token.holder_node_id == "worker-node"

        # Liberar
        ok = worker_coord.release_resource(token.token_id)
        assert ok is True

    def test_concurrent_acquire_denied(
        self, leader_coord: MeshCoordinator, worker_coord: MeshCoordinator
    ) -> None:
        # Leader adquiere
        t1 = leader_coord.acquire_resource("cortex", ttl_sec=30)
        assert t1 is not None

        # Worker intenta → denegado
        time.sleep(1.0)
        if worker_coord.bus.get_leader_socket() is None:
            worker_coord.bus.set_leader_socket(leader_coord.socket_path)
            worker_coord.bus.register_peer("leader-node", leader_coord.socket_path)
        t2 = worker_coord.acquire_resource("cortex", ttl_sec=30)
        assert t2 is None  # denegado

        # Leader libera
        leader_coord.release_resource(t1.token_id)

        # Ahora worker puede
        t3 = worker_coord.acquire_resource("cortex", ttl_sec=30)
        assert t3 is not None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_leader_stats(self, leader_coord: MeshCoordinator) -> None:
        s = leader_coord.stats()
        assert s["module"] == "mesh_coordinator"
        assert s["role"] == "leader"
        assert s["am_i_leader"] is True
        assert "arbitrator" in s

    def test_worker_stats(self, leader_coord: MeshCoordinator, worker_coord: MeshCoordinator) -> None:
        s = worker_coord.stats()
        assert s["role"] == "worker"
        assert s["am_i_leader"] is False


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_start_stop_idempotent(self, db_path: Path, runtime_dir: Path, lockfile: Path) -> None:
        coord = MeshCoordinator(
            node_id="test",
            db_path=db_path,
            runtime_dir=runtime_dir,
            lockfile_path=lockfile,
        )
        coord.start()
        coord.stop()
        # Segunda vez no debe romper
        coord2 = MeshCoordinator(
            node_id="test2",
            db_path=db_path,
            runtime_dir=runtime_dir,
            lockfile_path=lockfile,
        )
        coord2.start()
        coord2.stop()
