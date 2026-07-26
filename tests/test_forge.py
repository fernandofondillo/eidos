"""Tests del CapsuleForge — Fase 3.2."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.forge import (
    CapsuleDraft,
    CapsuleForge,
    CapsuleOntology,
    CapsuleRule,
    CapsuleTool,
    CapsuleTone,
    ForgeDecision,
    LLMForgeBackend,
    StubForgeBackend,
)
from eidos.core.sandbox import ToolSandbox
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
    return tmp_path / "capsules"


@pytest.fixture
def procedural(db_path: Path, capsules_dir: Path) -> ProceduralMemory:
    return ProceduralMemory(db_path=db_path, capsules_dir=capsules_dir)


@pytest.fixture
def forge(db_path: Path, procedural: ProceduralMemory) -> CapsuleForge:
    return CapsuleForge(db_path=db_path, procedural=procedural, backend=StubForgeBackend())


# ---------------------------------------------------------------------------
# StubForgeBackend
# ---------------------------------------------------------------------------


class TestStubForgeBackend:
    def test_forge_basic_capsule(self) -> None:
        backend = StubForgeBackend()
        draft = backend.forge("conviértete en experto en auditoría de código Rust")
        assert isinstance(draft, CapsuleDraft)
        assert "auditoría" in draft.name.lower() or "rust" in draft.name.lower() or "experto" in draft.name.lower()
        assert draft.genesis_confidence >= 0.7
        assert draft.tools == []  # stub no genera tools
        assert draft.smoke_test_passed is True

    def test_forge_empty_request_raises(self) -> None:
        with pytest.raises(ValueError):
            StubForgeBackend().forge("")

    def test_forge_extracts_domain_from_keywords(self) -> None:
        draft = StubForgeBackend().forge("necesito experto en Kubernetes")
        assert "kubernetes" in draft.ontology.domain.lower() or "kubernetes" in draft.name.lower()

    def test_forge_context_preserved(self) -> None:
        draft = StubForgeBackend().forge(
            "experto en ML",
            context={"requested_by": "auto_evolution", "parent_capsule_id": "parent-123"},
        )
        assert draft.requested_by == "auto_evolution"
        assert draft.parent_capsule_id == "parent-123"


# ---------------------------------------------------------------------------
# CapsuleDraft validation (Pydantic)
# ---------------------------------------------------------------------------


class TestCapsuleDraftValidation:
    def test_valid_draft(self) -> None:
        d = CapsuleDraft(
            name="Test Capsule",
            ontology=CapsuleOntology(domain="test"),
            genesis_confidence=0.8,
        )
        assert d.version == "1.0.0"
        assert d.tone.style == "technical"

    def test_invalid_version_rejected(self) -> None:
        with pytest.raises(Exception):
            CapsuleDraft(
                name="X",
                ontology=CapsuleOntology(domain="x"),
                genesis_confidence=0.8,
                version="1.0",  # no es semver válido
            )

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(Exception):
            CapsuleDraft(
                name="X",
                ontology=CapsuleOntology(domain="x"),
                genesis_confidence=1.5,
            )

    def test_name_too_short_rejected(self) -> None:
        with pytest.raises(Exception):
            CapsuleDraft(
                name="ab",  # < 3 chars
                ontology=CapsuleOntology(domain="x"),
                genesis_confidence=0.5,
            )


# ---------------------------------------------------------------------------
# CapsuleForge — pipeline completo con StubBackend
# ---------------------------------------------------------------------------


class TestCapsuleForgeStub:
    def test_forge_auto_approves_high_confidence(self, forge: CapsuleForge) -> None:
        # El stub genera confidence 0.7-0.95; forzamos uno alto con más keywords
        draft, decision = forge.forge("experto en Kubernetes Docker CI/CD Python Rust")
        assert decision == ForgeDecision.AUTO_APPROVED
        assert draft.smoke_test_passed is True

    def test_forge_pending_when_force_pending(self, forge: CapsuleForge) -> None:
        draft, decision = forge.forge("experto en ML", force_pending=True)
        assert decision == ForgeDecision.PENDING_APPROVAL

    def test_pending_draft_persisted(self, forge: CapsuleForge) -> None:
        draft, decision = forge.forge("experto en algo", force_pending=True)
        drafts = forge.list_drafts(status="pending")
        assert len(drafts) == 1
        assert drafts[0]["id"] == draft.id

    def test_approve_pending_draft(self, forge: CapsuleForge, procedural: ProceduralMemory) -> None:
        draft, _ = forge.forge("experto en algo", force_pending=True)
        ok = forge.approve(draft.id)
        assert ok is True
        # Debe estar ahora en procedural
        all_caps = procedural.list_all()
        assert any(c.name == draft.name for c in all_caps)

    def test_reject_pending_draft(self, forge: CapsuleForge) -> None:
        draft, _ = forge.forge("experto en algo", force_pending=True)
        ok = forge.reject(draft.id)
        assert ok is True
        drafts = forge.list_drafts(status="rejected")
        assert len(drafts) == 1

    def test_auto_approved_capsule_in_procedural(
        self, forge: CapsuleForge, procedural: ProceduralMemory
    ) -> None:
        draft, decision = forge.forge("experto en Kubernetes Docker Python Rust Go")
        assert decision == ForgeDecision.AUTO_APPROVED
        all_caps = procedural.list_all()
        assert any(c.name == draft.name for c in all_caps)
        assert any(c.genesis_confidence == draft.genesis_confidence for c in all_caps)

    def test_get_draft(self, forge: CapsuleForge) -> None:
        draft, _ = forge.forge("experto en algo", force_pending=True)
        fetched = forge.get_draft(draft.id)
        assert fetched is not None
        assert fetched["id"] == draft.id

    def test_get_draft_nonexistent(self, forge: CapsuleForge) -> None:
        assert forge.get_draft("nonexistent-id") is None

    def test_list_pending(self, forge: CapsuleForge) -> None:
        forge.forge("experto en a", force_pending=True)
        forge.forge("experto en b", force_pending=True)
        pending = forge.list_pending()
        assert len(pending) == 2


# ---------------------------------------------------------------------------
# CapsuleForge — smoke test de tools peligrosas
# ---------------------------------------------------------------------------


class TestCapsuleForgeToolValidation:
    def test_capsule_with_failing_tool_rejected(
        self, db_path: Path, procedural: ProceduralMemory
    ) -> None:
        """Un backend que genera una tool con código que crashea → rejected."""

        class FailingToolBackend:
            def forge(self, request, context=None):
                return CapsuleDraft(
                    name="Test Failing Tool",
                    ontology=CapsuleOntology(domain="test"),
                    tools=[
                        CapsuleTool(
                            name="broken",
                            entry_point="broken",
                            code="def broken():\n    raise RuntimeError('intentional')\n",
                        )
                    ],
                    genesis_confidence=0.95,  # alta, pero smoke test falla
                    smoke_test_passed=False,
                )

        forge = CapsuleForge(
            db_path=db_path,
            procedural=procedural,
            backend=FailingToolBackend(),
        )
        draft, decision = forge.forge("test")
        assert decision == ForgeDecision.REJECTED
        assert draft.smoke_test_passed is False

    def test_capsule_with_safe_tool_auto_approved(
        self, db_path: Path, procedural: ProceduralMemory
    ) -> None:
        class SafeToolBackend:
            def forge(self, request, context=None):
                return CapsuleDraft(
                    name="Test Safe Tool",
                    ontology=CapsuleOntology(domain="test"),
                    tools=[
                        CapsuleTool(
                            name="greet",
                            entry_point="greet",
                            code="def greet(name='world'):\n    return f'Hello, {name}!'\n",
                        )
                    ],
                    genesis_confidence=0.9,
                    smoke_test_passed=False,
                )

        forge = CapsuleForge(
            db_path=db_path,
            procedural=procedural,
            backend=SafeToolBackend(),
        )
        draft, decision = forge.forge("test")
        assert decision == ForgeDecision.AUTO_APPROVED
        assert draft.smoke_test_passed is True

    def test_capsule_with_dangerous_code_rejected(
        self, db_path: Path, procedural: ProceduralMemory
    ) -> None:
        """Código con exec() debe ser rechazado por AST validation."""

        class DangerousToolBackend:
            def forge(self, request, context=None):
                return CapsuleDraft(
                    name="Dangerous",
                    ontology=CapsuleOntology(domain="test"),
                    tools=[
                        CapsuleTool(
                            name="bad",
                            entry_point="bad",
                            code="def bad():\n    exec('import os')\n",
                        )
                    ],
                    genesis_confidence=0.95,
                    smoke_test_passed=False,
                )

        forge = CapsuleForge(
            db_path=db_path,
            procedural=procedural,
            backend=DangerousToolBackend(),
        )
        draft, decision = forge.forge("test")
        assert decision == ForgeDecision.REJECTED
        assert draft.smoke_test_passed is False
        assert "exec" in (draft.smoke_test_output or "").lower() or "ast" in (draft.smoke_test_output or "").lower()

    def test_high_risk_tool_name_forces_pending(
        self, db_path: Path, procedural: ProceduralMemory
    ) -> None:
        class HighRiskBackend:
            def forge(self, request, context=None):
                return CapsuleDraft(
                    name="Risky",
                    ontology=CapsuleOntology(domain="test"),
                    tools=[
                        CapsuleTool(
                            name="exec_command",  # en HIGH_RISK_TOOL_NAMES
                            entry_point="exec_command",
                            code="def exec_command():\n    return 'safe'\n",
                        )
                    ],
                    genesis_confidence=0.95,
                    smoke_test_passed=False,
                )

        forge = CapsuleForge(
            db_path=db_path,
            procedural=procedural,
            backend=HighRiskBackend(),
        )
        draft, decision = forge.forge("test")
        # Aunque smoke test pasa y confidence alta, tool de alto riesgo → pending
        assert decision == ForgeDecision.PENDING_APPROVAL
        assert draft.smoke_test_passed is True


# ---------------------------------------------------------------------------
# LLMForgeBackend — con mock de CortexHub
# ---------------------------------------------------------------------------


class TestLLMForgeBackend:
    def test_forge_with_mock_llm(self, db_path: Path) -> None:
        """Inyectamos un CortexHub mock con un LlamaClient que devuelve JSON válido."""
        import json

        class FakeClient:
            def complete(self, prompt, **kwargs):
                return json.dumps(
                    {
                        "name": "Experto en Testing",
                        "description": "Cápsula de testing automático.",
                        "ontology": {
                            "domain": "testing",
                            "entities": ["pytest", "mock"],
                            "relations": [{"subject": "test", "predicate": "usa", "object": "pytest"}],
                        },
                        "rules": [
                            {"id": "r1", "condition": "test falla", "action": "reportar", "priority": 1}
                        ],
                        "tone": {"style": "technical", "empathy": 5, "verbosity": 5},
                        "tools": [],
                        "genesis_confidence": 0.9,
                    }
                )

        class FakeHub:
            def get_monologue_backend(self, max_plan_steps=5, client=None):
                class FakeBackend:
                    _client = FakeClient()

                return FakeBackend()

        backend = LLMForgeBackend(cortex_hub=FakeHub())
        draft = backend.forge("experto en testing")
        assert draft.name == "Experto en Testing"
        assert draft.ontology.domain == "testing"
        assert draft.genesis_confidence == 0.9
        assert len(draft.rules) == 1

    def test_forge_degrades_to_stub_when_no_model(self, db_path: Path) -> None:
        class FakeHubNoModel:
            def get_monologue_backend(self, max_plan_steps=5, client=None):
                return None  # no hay modelo cargado

        backend = LLMForgeBackend(cortex_hub=FakeHubNoModel())
        draft = backend.forge("experto en algo")
        # Debe degradar a stub
        assert "experto" in draft.name.lower() or draft.ontology.domain
        assert draft.metadata.get("backend") == "stub"

    def test_forge_retries_on_invalid_json(self, db_path: Path) -> None:
        attempts = [0]

        class FlakeyClient:
            def complete(self, prompt, **kwargs):
                attempts[0] += 1
                if attempts[0] < 3:
                    return "esto no es JSON válido"
                import json
                return json.dumps(
                    {
                        "name": "Test",
                        "description": "",
                        "ontology": {"domain": "test"},
                        "rules": [],
                        "tone": {},
                        "tools": [],
                        "genesis_confidence": 0.7,
                    }
                )

        class FakeHub:
            def get_monologue_backend(self, max_plan_steps=5, client=None):
                class FakeBackend:
                    _client = FlakeyClient()

                return FakeBackend()

        backend = LLMForgeBackend(cortex_hub=FakeHub())
        draft = backend.forge("test")
        assert draft.name == "Test"
        assert attempts[0] >= 3  # hubo reintentos

    def test_forge_fails_after_max_retries(self, db_path: Path) -> None:
        class AlwaysBadClient:
            def complete(self, prompt, **kwargs):
                return "no json ever"

        class FakeHub:
            def get_monologue_backend(self, max_plan_steps=5, client=None):
                class FakeBackend:
                    _client = AlwaysBadClient()

                return FakeBackend()

        backend = LLMForgeBackend(cortex_hub=FakeHub())
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            backend.forge("test")
