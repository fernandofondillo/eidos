"""Tests del LeaderElection — Fase 4.

Tests con lockfiles reales (atómicos POSIX). No requiere sockets.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from eidos.mesh.bus import MeshBus
from eidos.mesh.election import LeaderElection
from eidos.mesh.protocol import NodeRole, PubTopic, pub
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
def bus(runtime_dir: Path) -> MeshBus:
    b = MeshBus(node_id="test-node", runtime_dir=runtime_dir)
    b.start()
    yield b
    b.stop()


@pytest.fixture
def election(lockfile: Path, bus: MeshBus) -> LeaderElection:
    return LeaderElection(
        node_id="test-node",
        lockfile_path=lockfile,
        bus=bus,
        heartbeat_interval_sec=0.5,
        leader_timeout_sec=1.5,
    )


# ---------------------------------------------------------------------------
# Adquisición de liderazgo
# ---------------------------------------------------------------------------


class TestAcquireLeadership:
    def test_first_acquire_becomes_leader(self, election: LeaderElection, lockfile: Path) -> None:
        role = election.try_acquire_leadership()
        assert role is NodeRole.LEADER
        assert election.am_i_leader is True
        assert lockfile.exists()

    def test_second_node_becomes_worker(self, lockfile: Path, bus: MeshBus) -> None:
        # Primera elección gana
        e1 = LeaderElection(
            node_id="node-1",
            lockfile_path=lockfile,
            bus=bus,
            heartbeat_interval_sec=0.5,
            leader_timeout_sec=1.5,
        )
        r1 = e1.try_acquire_leadership()
        assert r1 is NodeRole.LEADER

        # Segunda elección pierde (lockfile ya existe)
        e2 = LeaderElection(
            node_id="node-2",
            lockfile_path=lockfile,
            bus=bus,
            heartbeat_interval_sec=0.5,
            leader_timeout_sec=1.5,
        )
        r2 = e2.try_acquire_leadership()
        assert r2 is NodeRole.WORKER
        assert e2.am_i_leader is False
        assert e2.leader_id == "node-1"

    def test_lockfile_contains_node_id(self, election: LeaderElection, lockfile: Path) -> None:
        import json

        election.try_acquire_leadership()
        data = json.loads(lockfile.read_text(encoding="utf-8").strip())
        assert data["node_id"] == "test-node"
        assert data["pid"] == os.getpid()
        assert "hostname" in data


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


class TestRelease:
    def test_release_allows_reacquire(self, election: LeaderElection, lockfile: Path) -> None:
        election.try_acquire_leadership()
        assert election.am_i_leader is True
        election.release_leadership()
        assert election.am_i_leader is False
        assert not lockfile.exists()
        # Puede readquirir
        role = election.try_acquire_leadership()
        assert role is NodeRole.LEADER

    def test_release_stops_heartbeat(self, election: LeaderElection) -> None:
        election.try_acquire_leadership()
        election.start_heartbeat()
        time.sleep(0.2)
        election.release_leadership()
        # No debe haber thread activo
        assert election._heartbeat_thread is None or not election._heartbeat_thread.is_alive()


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_heartbeat_publishes_to_bus(self, election: LeaderElection, bus: MeshBus) -> None:
        received: list = []
        bus.subscribe(PubTopic.HEARTBEAT, lambda m: received.append(m))
        election.try_acquire_leadership()
        election.start_heartbeat()
        time.sleep(1.2)  # al menos 2 heartbeats
        election.stop_heartbeat()
        assert len(received) >= 1
        assert received[0].topic == "heartbeat"
        assert received[0].params["leader_id"] == "test-node"

    def test_on_heartbeat_updates_leader(self, election: LeaderElection, bus: MeshBus) -> None:
        # Simular heartbeat de otro Leader
        fake_msg = pub(
            source="other-leader",
            topic=PubTopic.HEARTBEAT,
            params={"leader_id": "other-leader", "pid": 12345},
        )
        election.on_heartbeat(fake_msg)
        assert election.leader_id == "other-leader"


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


class TestElectionRobustness:
    def test_election_idempotent_after_release(self, election: LeaderElection) -> None:
        election.try_acquire_leadership()
        election.release_leadership()
        election.try_acquire_leadership()
        election.release_leadership()
        # No debe romper
        assert election.am_i_leader is False

    def test_concurrent_elections_one_wins(self, lockfile: Path, bus: MeshBus) -> None:
        # Crear dos elecciones apuntando al mismo lockfile
        e1 = LeaderElection(node_id="n1", lockfile_path=lockfile, bus=bus,
                           heartbeat_interval_sec=0.5, leader_timeout_sec=1.5)
        e2 = LeaderElection(node_id="n2", lockfile_path=lockfile, bus=bus,
                           heartbeat_interval_sec=0.5, leader_timeout_sec=1.5)
        r1 = e1.try_acquire_leadership()
        r2 = e2.try_acquire_leadership()
        # Exactamente uno debe ser Leader
        leaders = sum(1 for r in [r1, r2] if r is NodeRole.LEADER)
        assert leaders == 1
