"""Tests del web server — Fase 5.

Tests con httpx (ASGI transport) — no requieren arrancar el server
en un puerto real. Verifican todos los endpoints REST.

Los tests de WebSocket usan la API de Starlette TestClient (síncrona).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from eidos.utils.persistence import apply_migrations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def initialized_app(tmp_path: Path):
    """Inicializa la FastAPI app con un EidosCore de test."""
    # Copiar migraciones a tmp
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    tmp_migrations = tmp_path / "data" / "migrations"
    tmp_migrations.mkdir(parents=True)
    for f in proj_migrations.glob("*.sql"):
        (tmp_migrations / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    # Config mínima de test
    config = {
        "core": {
            "monologue_backend": "stub",
            "confidence_threshold": 0.4,
            "persist_monologues": False,
            "max_plan_steps": 5,
        },
        "memory": {
            "sensory": {"window_size": 30},
            "episodic": {
                "db_path": "data/eidos.db",
                "embedding_dim": 64,
                "max_events": 100,
            },
            "semantic": {"graph_path": "data/graph.json"},
            "procedural": {
                "capsules_dir": "data/capsules",
                "default_ttl_days": 7,
            },
        },
        "mesh": {"enabled": False},
        "logging": {"level": "WARNING", "format": "console"},
    }

    from eidos.web.server import init_core

    init_core(config, tmp_path)

    from eidos.web.server import app

    return app


@pytest.fixture
async def client(initialized_app):
    """Cliente HTTP async para tests REST."""
    transport = ASGITransport(app=initialized_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_health_endpoint(self, client: AsyncClient) -> None:
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "backend" in data
        assert "mesh_enabled" in data


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class TestChat:
    async def test_chat_returns_response(self, client: AsyncClient) -> None:
        r = await client.post("/api/chat", json={"message": "hola EIDOS"})
        assert r.status_code == 200
        data = r.json()
        assert "text" in data
        assert "monologue_id" in data
        assert "route_type" in data
        assert "confidence" in data
        assert "reward_delta" in data
        assert "monologue_backend" in data
        assert data["monologue"] is not None
        assert "observation" in data["monologue"]
        assert "hypothesis" in data["monologue"]
        assert "plan" in data["monologue"]

    async def test_chat_empty_message_rejected(self, client: AsyncClient) -> None:
        r = await client.post("/api/chat", json={"message": ""})
        assert r.status_code == 422

    async def test_chat_with_context(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/chat",
            json={"message": "test", "context": "previous conversation"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    async def test_stats_returns_5_layers(self, client: AsyncClient) -> None:
        r = await client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "sensory" in data
        assert "episodic" in data
        assert "semantic" in data
        assert "procedural" in data
        assert "metacognitive" in data
        for layer in ["sensory", "episodic", "semantic", "procedural", "metacognitive"]:
            assert data[layer]["layer"] == layer


# ---------------------------------------------------------------------------
# Capsules
# ---------------------------------------------------------------------------


class TestCapsules:
    async def test_list_capsules_empty(self, client: AsyncClient) -> None:
        r = await client.get("/api/capsules")
        assert r.status_code == 200
        data = r.json()
        assert "drafts" in data
        assert "active" in data
        assert isinstance(data["drafts"], list)
        assert isinstance(data["active"], list)

    async def test_forge_creates_draft(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/capsules/forge",
            json={"request": "experto en Kubernetes", "force_pending": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert "draft" in data
        assert "decision" in data
        assert data["decision"] in ("auto_approved", "pending_approval", "rejected")
        assert data["draft"]["name"]

    async def test_forge_and_approve(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/capsules/forge",
            json={"request": "experto en ML", "force_pending": True},
        )
        draft_id = r.json()["draft"]["id"]
        r2 = await client.post("/api/capsules/approve", json={"draft_id": draft_id})
        assert r2.status_code == 200
        assert r2.json()["approved"] is True

    async def test_reject_draft(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/capsules/forge",
            json={"request": "experto en algo", "force_pending": True},
        )
        draft_id = r.json()["draft"]["id"]
        r2 = await client.post("/api/capsules/reject", json={"draft_id": draft_id})
        assert r2.status_code == 200
        assert r2.json()["rejected"] is True

    async def test_approve_nonexistent_returns_404(self, client: AsyncClient) -> None:
        r = await client.post("/api/capsules/approve", json={"draft_id": "nonexistent"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Mesh status
# ---------------------------------------------------------------------------


class TestMeshStatus:
    async def test_mesh_disabled(self, client: AsyncClient) -> None:
        r = await client.get("/api/mesh/status")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is False


# ---------------------------------------------------------------------------
# Motivation
# ---------------------------------------------------------------------------


class TestMotivation:
    async def test_motivation_returns_stats(self, client: AsyncClient) -> None:
        r = await client.get("/api/motivation")
        assert r.status_code == 200
        data = r.json()
        assert "session_total_reward" in data
        assert "by_driver" in data
        assert "recent_rewards" in data
        assert "satisfaction_streak" in data

    async def test_motivation_after_negative_chat(self, client: AsyncClient) -> None:
        await client.post("/api/chat", json={"message": "no, eso está mal"})
        r = await client.get("/api/motivation")
        data = r.json()
        assert len(data["recent_rewards"]) >= 1


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------


class TestEvolution:
    async def test_evolution_returns_stats(self, client: AsyncClient) -> None:
        r = await client.get("/api/evolution")
        assert r.status_code == 200
        data = r.json()
        assert "auto_forge_enabled" in data
        assert "total_capsules" in data
        assert "favorites" in data
        assert "promotion_threshold" in data

    async def test_evolution_triggered_by_specialization(
        self, client: AsyncClient
    ) -> None:
        r = await client.post(
            "/api/chat", json={"message": "conviértete en experto en Kubernetes"}
        )
        data = r.json()
        if data.get("evolution_event"):
            assert data["evolution_event"]["topic"]
            assert data["evolution_event"]["decision"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    async def test_get_config(self, client: AsyncClient) -> None:
        r = await client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert "core" in data
        assert "memory" in data


# ---------------------------------------------------------------------------
# WebSocket — con Starlette TestClient (síncrono)
# ---------------------------------------------------------------------------


class TestWebSocket:
    def test_ws_chat(self, initialized_app) -> None:
        """Test del WebSocket con Starlette TestClient."""
        from starlette.testclient import TestClient

        with TestClient(initialized_app) as tc:
            with tc.websocket_connect("/ws/chat") as ws:
                ws.send_json({"type": "chat", "message": "hola EIDOS"})
                # Recibir monologue
                msg1 = ws.receive_json()
                assert msg1["type"] == "monologue"
                assert "observation" in msg1["data"]
                # Recibir response
                msg2 = ws.receive_json()
                assert msg2["type"] == "response"
                assert "text" in msg2["data"]

    def test_ws_ping(self, initialized_app) -> None:
        from starlette.testclient import TestClient

        with TestClient(initialized_app) as tc:
            with tc.websocket_connect("/ws/chat") as ws:
                ws.send_json({"type": "ping"})
                msg = ws.receive_json()
                assert msg["type"] == "pong"

    def test_ws_invalid_message(self, initialized_app) -> None:
        from starlette.testclient import TestClient

        with TestClient(initialized_app) as tc:
            with tc.websocket_connect("/ws/chat") as ws:
                ws.send_json({"type": "invalid"})
                msg = ws.receive_json()
                assert msg["type"] == "error"
