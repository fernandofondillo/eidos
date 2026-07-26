"""Tests del ActionRouter y de EidosCore end-to-end — Fase 1.1."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.engine import EidosCore, Response
from eidos.core.monologue import Monologue
from eidos.core.router import ActionRouter, RouteType


# ---------------------------------------------------------------------------
# ActionRouter
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
# EidosCore end-to-end
# ---------------------------------------------------------------------------


class TestEidosCore:
    def test_think_and_respond_returns_response(self, tmp_path: Path) -> None:
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

    def test_response_includes_route_marker(self, tmp_path: Path) -> None:
        core = EidosCore(monologue_backend="stub", monologues_dir=None)
        resp = core.think_and_respond("test input")
        assert "backend=stub" in resp.text
        assert "route=" in resp.text

    def test_persistence_across_turns(self, tmp_path: Path) -> None:
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=tmp_path,
        )
        core.think_and_respond("primera pregunta")
        core.think_and_respond("segunda pregunta")
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 2, "Cada turno debe persistir su monólogo."

    def test_empty_input_raises(self, tmp_path: Path) -> None:
        core = EidosCore(monologue_backend="stub", monologues_dir=None)
        with pytest.raises((ValueError, Exception)):
            core.think_and_respond("")
