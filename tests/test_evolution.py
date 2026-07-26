"""Tests del EvolutionLoop — Fase 3.3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eidos.core.evolution import EvolutionLoop
from eidos.core.forge import CapsuleForge, StubForgeBackend
from eidos.core.monologue import Monologue
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


@pytest.fixture
def evolution(forge: CapsuleForge, procedural: ProceduralMemory) -> EvolutionLoop:
    return EvolutionLoop(forge=forge, procedural=procedural, auto_forge=True)


# ---------------------------------------------------------------------------
# Detección de necesidad
# ---------------------------------------------------------------------------


class TestNeedDetection:
    def test_explicit_request_detected(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("Conviértete en experto en auditoría de Rust")
        assert topic is not None
        assert "auditoría" in topic.lower() or "rust" in topic.lower()

    def test_necesito_pattern_detected(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("Necesito que seas experto en Kubernetes")
        assert topic is not None
        assert "kubernetes" in topic.lower()

    def test_crea_capsula_pattern_detected(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("Crea una cápsula para análisis de logs")
        assert topic is not None
        assert "análisis" in topic.lower() or "logs" in topic.lower()

    def test_actua_como_pattern_detected(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("Actúa como experto en ciberseguridad")
        assert topic is not None
        assert "ciberseguridad" in topic.lower()

    def test_no_need_returns_none(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("¿Qué es EIDOS?")
        assert topic is None

    def test_greeting_no_need(self, evolution: EvolutionLoop) -> None:
        topic = evolution.detect_need("Hola, ¿cómo estás?")
        assert topic is None


# ---------------------------------------------------------------------------
# process_turn — ciclo completo
# ---------------------------------------------------------------------------


class TestProcessTurn:
    def test_turn_with_need_triggers_forge(
        self, evolution: EvolutionLoop, forge: CapsuleForge
    ) -> None:
        result = evolution.process_turn("Conviértete en experto en machine learning")
        assert result is not None
        assert "topic" in result
        assert "draft_id" in result
        assert result["decision"] in ("auto_approved", "pending_approval")

    def test_turn_without_need_returns_none(self, evolution: EvolutionLoop) -> None:
        result = evolution.process_turn("¿Qué hora es?")
        assert result is None

    def test_auto_forge_disabled_doesnt_forge(
        self, forge: CapsuleForge, procedural: ProceduralMemory
    ) -> None:
        evo = EvolutionLoop(forge=forge, procedural=procedural, auto_forge=False)
        result = evo.process_turn("Conviértete en experto en ML")
        assert result is not None
        assert result.get("auto_forge_disabled") is True
        assert "draft_id" not in result

    def test_forge_failure_handled(
        self, forge: CapsuleForge, procedural: ProceduralMemory
    ) -> None:
        """Si el forge lanza excepción, process_turn no debe propagar."""
        # Reemplazar backend con uno que falla
        class FailingBackend:
            def forge(self, request, context=None):
                raise RuntimeError("intentional failure")

        forge._backend = FailingBackend()
        evo = EvolutionLoop(forge=forge, procedural=procedural, auto_forge=True)
        result = evo.process_turn("Conviértete en experto en Rust")
        assert result is not None
        assert "error" in result

    def test_heuristic_via_monologue(self, evolution: EvolutionLoop) -> None:
        """Monólogo con hipótesis que indica necesidad debe disparar detección."""
        m = Monologue(
            input_summary="necesito especialización",
            observation="obs",
            hypothesis="El usuario necesita experto en análisis de datos. Falta especialización.",
            plan=["Crear cápsula"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        topic = evolution.detect_need("análisis datos", monologue=m)
        assert topic is not None


# ---------------------------------------------------------------------------
# Promoción a favorita
# ---------------------------------------------------------------------------


class TestPromotionToFavorite:
    def test_promotes_high_use_capsule(
        self, evolution: EvolutionLoop, procedural: ProceduralMemory
    ) -> None:
        # Crear una cápsula y simular usos múltiples recientes
        rec = procedural.store(
            name="Popular Cap",
            version="1.0.0",
            description="",
            content={},
        )
        # Simular 4 usos (threshold = 3)
        for _ in range(4):
            procedural.mark_used(rec.id)

        promoted = evolution.check_promotions()
        assert rec.id in promoted

        fetched = procedural.get(rec.id)
        assert fetched is not None
        assert fetched.favorite is True

    def test_does_not_promote_low_use(
        self, evolution: EvolutionLoop, procedural: ProceduralMemory
    ) -> None:
        rec = procedural.store(name="Low Use", version="1.0.0", description="", content={})
        procedural.mark_used(rec.id)  # solo 1 uso

        promoted = evolution.check_promotions()
        assert rec.id not in promoted

    def test_does_not_promote_old_use(
        self, evolution: EvolutionLoop, procedural: ProceduralMemory
    ) -> None:
        """Si el último uso fue hace más de 24h, no promover."""
        rec = procedural.store(name="Old", version="1.0.0", description="", content={})
        # Forzar 4 usos y luego un last_used antiguo
        for _ in range(4):
            procedural.mark_used(rec.id)
        # Modificar last_used a 48h atrás
        import sqlite3

        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = sqlite3.connect(procedural._db_path)
        conn.execute("UPDATE capsules SET last_used = ? WHERE id = ?", (old_ts, rec.id))
        conn.commit()
        conn.close()

        promoted = evolution.check_promotions()
        assert rec.id not in promoted

    def test_does_not_promote_already_favorite(
        self, evolution: EvolutionLoop, procedural: ProceduralMemory
    ) -> None:
        rec = procedural.store(
            name="Already Fav", version="1.0.0", description="", content={}, favorite=True
        )
        for _ in range(5):
            procedural.mark_used(rec.id)

        promoted = evolution.check_promotions()
        assert rec.id not in promoted  # ya es favorita, no se "promueve" de nuevo


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestEvolutionStats:
    def test_stats_returns_metrics(self, evolution: EvolutionLoop) -> None:
        s = evolution.stats()
        assert s["module"] == "evolution"
        assert s["auto_forge_enabled"] is True
        assert "total_capsules" in s
        assert "promotion_threshold" in s
        assert s["promotion_threshold"] == 3

    def test_stats_reflects_capsules(
        self, evolution: EvolutionLoop, procedural: ProceduralMemory
    ) -> None:
        procedural.store(name="C1", version="1.0.0", description="", content={})
        procedural.store(name="C2", version="1.0.0", description="", content={}, favorite=True)
        s = evolution.stats()
        assert s["total_capsules"] == 2
        assert s["favorites"] == 1
