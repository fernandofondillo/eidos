"""Tests del MonologueGenerator y su backend stub — Fase 1.1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eidos.core.monologue import (
    Monologue,
    MonologueGenerator,
    StubMonologueBackend,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stub() -> StubMonologueBackend:
    return StubMonologueBackend()


@pytest.fixture
def generator(tmp_path: Path) -> MonologueGenerator:
    return MonologueGenerator(backend="stub", monologues_dir=tmp_path, max_plan_steps=5)


# ---------------------------------------------------------------------------
# Schema Pydantic
# ---------------------------------------------------------------------------


class TestMonologueSchema:
    def test_valid_monologue(self) -> None:
        m = Monologue(
            input_summary="test",
            observation="obs",
            hypothesis="hyp",
            plan=["step1", "step2"],
            risk="none",
            confidence=0.8,
            backend="stub",
        )
        assert m.id  # UUID auto-generado
        assert m.timestamp is not None
        assert m.backend == "stub"

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Monologue(
                input_summary="t",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=1.5,
                backend="stub",
            )

    def test_confidence_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Monologue(
                input_summary="t",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=-0.1,
                backend="stub",
            )

    def test_empty_plan_step_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Monologue(
                input_summary="t",
                observation="o",
                hypothesis="h",
                plan=["valid", ""],
                risk="none",
                confidence=0.5,
                backend="stub",
            )

    def test_empty_plan_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Monologue(
                input_summary="t",
                observation="o",
                hypothesis="h",
                plan=[],
                risk="none",
                confidence=0.5,
                backend="stub",
            )

    def test_to_json_file_roundtrip(self, tmp_path: Path) -> None:
        m = Monologue(
            input_summary="test",
            observation="obs",
            hypothesis="hyp",
            plan=["a", "b"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        out = m.to_json_file(tmp_path)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["id"] == m.id
        assert data["plan"] == ["a", "b"]


# ---------------------------------------------------------------------------
# Stub backend — determinismo
# ---------------------------------------------------------------------------


class TestStubBackend:
    def test_empty_input_rejected(self, stub: StubMonologueBackend) -> None:
        with pytest.raises(ValueError):
            stub.generate("")

    def test_deterministic_same_input_same_output(self, stub: StubMonologueBackend) -> None:
        m1 = stub.generate("¿Qué es EIDOS?")
        m2 = stub.generate("¿Qué es EIDOS?")
        # Mismo input → misma observación, hipótesis, plan, confianza.
        # (id y timestamp sí cambian, pero el resto no.)
        assert m1.observation == m2.observation
        assert m1.hypothesis == m2.hypothesis
        assert m1.plan == m2.plan
        assert m1.confidence == m2.confidence

    def test_question_intent_detected(self, stub: StubMonologueBackend) -> None:
        m = stub.generate("¿Qué es EIDOS?")
        assert "question" in m.hypothesis or "responder" in m.hypothesis
        assert len(m.plan) >= 1

    def test_command_intent_detected(self, stub: StubMonologueBackend) -> None:
        m = stub.generate("Crea un módulo de logging")
        assert len(m.plan) >= 3
        assert any("ejecutar" in p.lower() or "action" in p.lower() or "validar" in p.lower() for p in m.plan)

    def test_confidence_in_range(self, stub: StubMonologueBackend) -> None:
        for text in ["hola", "¿Qué es EIDOS?", "Crea algo", "x" * 500]:
            m = stub.generate(text)
            assert 0.0 <= m.confidence <= 1.0

    def test_keywords_extracted(self, stub: StubMonologueBackend) -> None:
        m = stub.generate("Diseña una cápsula para auditar código Rust")
        # Al menos una keyword significativa
        assert "cápsula" in m.observation.lower() or "rust" in m.observation.lower() or "auditar" in m.observation.lower()

    def test_risk_set_when_confidence_low(self, stub: StubMonologueBackend) -> None:
        # Input muy corto y ambiguo → confianza baja → risk informativo
        m = stub.generate("hola")
        if m.confidence < 0.5:
            assert m.risk != "none"


# ---------------------------------------------------------------------------
# MonologueGenerator — fachada
# ---------------------------------------------------------------------------


class TestMonologueGenerator:
    def test_stub_backend_default(self, tmp_path: Path) -> None:
        gen = MonologueGenerator(backend="stub")
        m = gen.generate("test input")
        assert m.backend == "stub"

    def test_unknown_backend_rejected(self) -> None:
        with pytest.raises(ValueError):
            MonologueGenerator(backend="unknown_backend")  # type: ignore[arg-type]

    def test_llama_cpp_not_implemented_yet(self) -> None:
        with pytest.raises(NotImplementedError):
            MonologueGenerator(backend="llama_cpp")

    def test_persist_monologue_to_disk(self, generator: MonologueGenerator, tmp_path: Path) -> None:
        m = generator.generate("¿Qué es EIDOS?")
        out = tmp_path / f"{m.id}.json"
        assert out.exists(), "Monologue should be persisted as JSON."
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["input_summary"].startswith("¿Qué es EIDOS?")

    def test_plan_truncated_to_max_steps(self, tmp_path: Path) -> None:
        gen = MonologueGenerator(backend="stub", monologues_dir=None, max_plan_steps=2)
        m = gen.generate("Crea algo complejo con muchos pasos")
        assert len(m.plan) <= 2

    def test_no_persistence_when_dir_none(self) -> None:
        gen = MonologueGenerator(backend="stub", monologues_dir=None)
        m = gen.generate("test")  # No debe lanzar
        assert m.id
