"""Tests del ResourceArbitrator — Fase 4."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eidos.mesh.arbitrator import ResourceArbitrator, ResourceToken
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def arbitrator(db_path: Path) -> ResourceArbitrator:
    return ResourceArbitrator(db_path=db_path, leader_node_id="leader-1")


# ---------------------------------------------------------------------------
# Adquisición básica
# ---------------------------------------------------------------------------


class TestAcquire:
    def test_acquire_returns_token(self, arbitrator: ResourceArbitrator) -> None:
        token = arbitrator.acquire(resource="cortex", holder_node_id="worker-1", ttl_sec=30)
        assert token is not None
        assert token.resource == "cortex"
        assert token.holder_node_id == "worker-1"
        assert token.token_id  # UUID

    def test_acquire_denied_when_busy(self, arbitrator: ResourceArbitrator) -> None:
        t1 = arbitrator.acquire(resource="cortex", holder_node_id="worker-1", ttl_sec=30)
        assert t1 is not None
        t2 = arbitrator.acquire(resource="cortex", holder_node_id="worker-2", ttl_sec=30)
        assert t2 is None  # denegado

    def test_acquire_same_holder_renews(self, arbitrator: ResourceArbitrator) -> None:
        t1 = arbitrator.acquire(resource="cortex", holder_node_id="worker-1", ttl_sec=30)
        assert t1 is not None
        # Mismo holder pide de nuevo → renueva (mismo token_id, expira extendido)
        t2 = arbitrator.acquire(resource="cortex", holder_node_id="worker-1", ttl_sec=60)
        assert t2 is not None
        assert t2.token_id == t1.token_id
        assert t2.expires_at != t1.expires_at

    def test_acquire_invalid_args_raises(self, arbitrator: ResourceArbitrator) -> None:
        with pytest.raises(ValueError):
            arbitrator.acquire(resource="", holder_node_id="w")
        with pytest.raises(ValueError):
            arbitrator.acquire(resource="cortex", holder_node_id="")


# ---------------------------------------------------------------------------
# Liberación
# ---------------------------------------------------------------------------


class TestRelease:
    def test_release_frees_token(self, arbitrator: ResourceArbitrator) -> None:
        t = arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        assert t is not None
        ok = arbitrator.release(t.token_id)
        assert ok is True
        # Ahora otro puede adquirir
        t2 = arbitrator.acquire(resource="cortex", holder_node_id="w2", ttl_sec=30)
        assert t2 is not None

    def test_release_nonexistent_returns_false(self, arbitrator: ResourceArbitrator) -> None:
        assert arbitrator.release("nonexistent-id") is False

    def test_release_already_released_returns_false(self, arbitrator: ResourceArbitrator) -> None:
        t = arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        assert t is not None
        assert arbitrator.release(t.token_id) is True
        # Segunda liberación → False
        assert arbitrator.release(t.token_id) is False

    def test_release_all_for_holder(self, arbitrator: ResourceArbitrator) -> None:
        arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        arbitrator.acquire(resource="memory_write", holder_node_id="w1", ttl_sec=30)
        released = arbitrator.release_all_for_holder("w1")
        assert released == 2


# ---------------------------------------------------------------------------
# TTL y expiración
# ---------------------------------------------------------------------------


class TestExpiry:
    def test_expire_due_releases_expired_tokens(self, arbitrator: ResourceArbitrator) -> None:
        # Token con TTL 1s
        t = arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=1)
        assert t is not None
        # Esperar a que expire
        time.sleep(1.5)
        expired = arbitrator.expire_due()
        assert expired >= 1
        # Ahora otro puede adquirir
        t2 = arbitrator.acquire(resource="cortex", holder_node_id="w2", ttl_sec=30)
        assert t2 is not None

    def test_get_active_token(self, arbitrator: ResourceArbitrator) -> None:
        t = arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        assert t is not None
        active = arbitrator.get_active_token("cortex")
        assert active is not None
        assert active.token_id == t.token_id

    def test_list_active(self, arbitrator: ResourceArbitrator) -> None:
        arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        arbitrator.acquire(resource="memory_write", holder_node_id="w1", ttl_sec=30)
        active = arbitrator.list_active()
        assert len(active) == 2
        resources = {t.resource for t in active}
        assert resources == {"cortex", "memory_write"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_returns_metrics(self, arbitrator: ResourceArbitrator) -> None:
        arbitrator.acquire(resource="cortex", holder_node_id="w1", ttl_sec=30)
        s = arbitrator.stats()
        assert s["module"] == "arbitrator"
        assert s["leader_id"] == "leader-1"
        assert s["active_tokens"] == 1
        assert s["by_resource"]["cortex"] == 1
        assert s["total_ever"] == 1


# ---------------------------------------------------------------------------
# ResourceToken
# ---------------------------------------------------------------------------


class TestResourceToken:
    def test_is_expired_with_past_expiry(self) -> None:
        token = ResourceToken(
            token_id="x",
            resource="cortex",
            holder_node_id="w",
            acquired_at="2020-01-01T00:00:00.000000Z",
            expires_at="2020-01-01T00:00:01.000000Z",
        )
        assert token.is_expired() is True
        assert token.is_active() is False

    def test_is_active_with_future_expiry(self) -> None:
        future = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        token = ResourceToken(
            token_id="x",
            resource="cortex",
            holder_node_id="w",
            acquired_at="2026-01-01T00:00:00.000000Z",
            expires_at=future,
        )
        assert token.is_expired() is False
        assert token.is_active() is True

    def test_released_token_is_expired(self) -> None:
        token = ResourceToken(
            token_id="x",
            resource="cortex",
            holder_node_id="w",
            acquired_at="2026-01-01T00:00:00.000000Z",
            expires_at="2099-01-01T00:00:00.000000Z",
            released_at="2026-01-01T00:00:05.000000Z",
        )
        assert token.is_expired() is True
