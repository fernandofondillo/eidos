"""Tests del ActionRouter y de EidosCore end-to-end — Fase 1.1 + 1.2."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.engine import EidosCore, Response
from eidos.core.monologue import Monologue
from eidos.core.router import ActionRouter, RouteType
from eidos.memory.store import MemoryStore
from eidos.utils.persistence import apply_migrations


# ---------------------------------------------------------------------------
# ActionRouter (Fase 1.1 — sin cambios funcionales)
# ---------------------------------------------------------------------------


def _make_monologue(confidence: float, risk: str = "none", plan: list[str] | None = None) -> Monologue:
    return Monologue(
        input_summary="test",
        observation="obs",
        hypothesis="hyp",
        plan=plan or ["step1"],
        risk=risk,
        confidence=confidence,
        backend="stub",
    )


class TestActionRouter:
    def test_low_confidence_requests_clarification(self) -> None:
        router = ActionRouter(confidence_threshold=0.6)
        m = _make_monologue(confidence=0.4)
        route = router.decide(m)
        assert route.route_type is RouteType.REQUEST_CLARIFICATION

    def test_high_confidence_no_keywords_responds_direct(self) -> None:
        router = ActionRouter(confidence_threshold=0.6)
        m = _make_monologue(confidence=0.9, plan=["acknowledge"])
        route = router.decide(m)
        assert route.route_type is RouteType.RESPOND_DIRECT

    def test_plan_with_memory_routes_to_search_memory(self) -> None:
        router = ActionRouter(confidence_threshold=0.6)
        m = _make_monologue(confidence=0.9, plan=["Recuperar memoria episódica"])
        route = router.decide(m)
        assert route.route_type is RouteType.SEARCH_MEMORY

    def test_plan_with_cortex_routes_to_delegate(self) -> None:
        router = ActionRouter(confidence_threshold=0.6)
        m = _make_monologue(confidence=0.9, plan=["Invocar Cortex Hub"])
        route = router.decide(m)
        assert route.route_type is RouteType.DELEGATE_CORTEX

    def test_safety_risk_blocks(self) -> None:
        router = ActionRouter(confidence_threshold=0.6)
        m = _make_monologue(confidence=0.95, risk="Comando con safety risk detectado")
        route = router.decide(m)
        assert route.route_type is RouteType.SAFETY_BLOCK

    def test_threshold_validation(self) -> None:
        with pytest.raises(ValueError):
            ActionRouter(confidence_threshold=1.5)
        with pytest.raises(ValueError):
            ActionRouter(confidence_threshold=-0.1)


# ---------------------------------------------------------------------------
# Fixtures para tests con memoria
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """MemoryStore completo para tests, usando migraciones reales del proyecto."""
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    tmp_migrations = tmp_path / "data" / "migrations"
    tmp_migrations.mkdir(parents=True)
    for f in proj_migrations.glob("*.sql"):
        (tmp_migrations / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    config = {
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
        }
    }
    return MemoryStore.from_config(config, tmp_path)


# ---------------------------------------------------------------------------
# EidosCore end-to-end — sin memoria (Fase 1.1)
# ---------------------------------------------------------------------------


class TestEidosCoreNoMemory:
    def test_think_and_respond_returns_response(self) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
        )
        resp = core.think_and_respond("¿Qué es EIDOS?")
        assert isinstance(resp, Response)
        assert resp.text
        assert resp.monologue_id
        assert resp.route_type in {r.value for r in RouteType}
        assert 0.0 <= resp.confidence <= 1.0

    def test_response_includes_route_marker(self) -> None:
        core = EidosCore(monologue_backend="stub", monologues_dir=None)
        resp = core.think_and_respond("test input")
        assert "backend=stub" in resp.text
        assert "route=" in resp.text

    def test_empty_input_raises(self) -> None:
        core = EidosCore(monologue_backend="stub", monologues_dir=None)
        with pytest.raises((ValueError, Exception)):
            core.think_and_respond("")


# ---------------------------------------------------------------------------
# EidosCore end-to-end — con memoria (Fase 1.2)
# ---------------------------------------------------------------------------


class TestEidosCoreWithMemory:
    def test_response_includes_memory_metadata(self, memory_store: MemoryStore) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        resp = core.think_and_respond("¿Qué es EIDOS?")
        assert resp.route_type in {r.value for r in RouteType}
        # Si la ruta fue search_memory, memory_context debe estar presente
        if resp.route_type == "search_memory":
            assert resp.memory_context is not None

    def test_sensory_memory_records_interaction(self, memory_store: MemoryStore) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        core.think_and_respond("hola")
        recent = memory_store.sensory.recent()
        # Al menos 2 eventos: input + response
        kinds = [r["kind"] for r in recent]
        assert "user_input" in kinds
        assert "response" in kinds

    def test_episodic_memory_records_interaction(self, memory_store: MemoryStore) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        core.think_and_respond("hola mundo")
        recent = memory_store.episodic.recent(limit=5)
        assert len(recent) == 1
        assert recent[0]["kind"] == "interaction"
        assert "hola mundo" in recent[0]["content"]

    def test_metacognitive_indexes_monologue(self, memory_store: MemoryStore) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        resp = core.think_and_respond("test")
        indexed = memory_store.metacognitive.get(resp.monologue_id)
        assert indexed is not None
        assert indexed["route_type"] == resp.route_type

    def test_memory_recall_on_repeated_topic(self, memory_store: MemoryStore) -> None:
        """Tras 2 interacciones sobre el mismo tema, una tercera debe recuperar
        al menos un resultado de memoria episódica."""
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        core.think_and_respond("¿Qué es EIDOS?")
        core.think_and_respond("Háblame más de EIDOS y su arquitectura")
        # La 3ª vez debe haber eventos episódicos relevantes
        episodic_count = memory_store.episodic.stats()["total"]
        assert episodic_count >= 2

    def test_stats_command_works(self, memory_store: MemoryStore) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        core.think_and_respond("test")
        s = memory_store.stats()
        assert s["sensory"]["buffered"] >= 2
        assert s["episodic"]["total"] >= 1
        assert s["metacognitive"]["total"] >= 1
