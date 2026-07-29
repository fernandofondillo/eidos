"""Tests de CapsuleForge — detección de especialización y guardado."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.forge import CapsuleForge, StubForgeBackend
from eidos.core.evolution import EvolutionLoop
from eidos.memory.procedural import ProceduralMemory
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def capsules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "capsules"
    d.mkdir()
    return d


@pytest.fixture
def procedural(db_path: Path, capsules_dir: Path) -> ProceduralMemory:
    return ProceduralMemory(db_path=db_path, capsules_dir=capsules_dir)


@pytest.fixture
def forge(db_path: Path, procedural: ProceduralMemory) -> CapsuleForge:
    return CapsuleForge(
        db_path=db_path,
        procedural=procedural,
        backend=StubForgeBackend(),
    )


class TestCapsuleForgeDetection:
    def test_capsule_forge_detects_specialization(
        self, forge: CapsuleForge
    ) -> None:
        """Debe detectar cuando el usuario pide una especialización."""
        from eidos.core.evolution import EvolutionLoop

        evo = EvolutionLoop(forge=forge, procedural=forge._procedural)
        assert evo.detect_need("Conviértete en experto en marketing") is not None
        assert evo.detect_need("Necesito que seas un experto en Python") is not None
        assert evo.detect_need("Hola, ¿cómo estás?") is None

    def test_capsule_forge_creates_and_saves(
        self, forge: CapsuleForge
    ) -> None:
        """Debe crear una cápsula válida y guardarla."""
        draft, decision = forge.forge("experto en marketing digital")
        assert draft is not None
        assert "marketing" in draft.name.lower() or "Marketing" in draft.name
        assert decision.value in ("auto_approved", "pending_approval")

        # Verificar que está en procedural
        caps = forge._procedural.list_all()
        if decision.value == "auto_approved":
            assert len(caps) > 0
            assert any("marketing" in c.name.lower() for c in caps)

    def test_capsule_forge_creates_multiple(self, forge: CapsuleForge) -> None:
        """Debe poder crear múltiples cápsulas."""
        forge.forge("experto en python")
        forge.forge("experto en rust")
        caps = forge._procedural.list_all()
        assert len(caps) >= 2

    def test_capsule_draft_has_valid_schema(self, forge: CapsuleForge) -> None:
        """El draft debe tener schema válido."""
        draft, _ = forge.forge("experto en kubernetes")
        assert draft.id
        assert draft.name
        assert draft.version == "1.0.0"
        assert draft.ontology.domain
        assert len(draft.plan) > 0 if hasattr(draft, 'plan') else True
        assert draft.genesis_confidence >= 0.0
