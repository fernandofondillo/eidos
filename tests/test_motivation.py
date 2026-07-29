"""Tests del MotivationModule — Fase 1.3."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.motivation import MotivationModule, RewardDriver
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def motivation(db_path: Path) -> MotivationModule:
    return MotivationModule(db_path=db_path, procedural=None)


# ---------------------------------------------------------------------------
# Driver: curiosidad (reducción de incertidumbre)
# ---------------------------------------------------------------------------


class TestCuriosityDriver:
    def test_first_confidence_no_reward(self, motivation: MotivationModule) -> None:
        # Sin historial previo, no hay delta de curiosidad
        delta = motivation.observe_confidence(0.7)
        assert delta == 0.0

    def test_confidence_increase_above_threshold_gives_reward(
        self, motivation: MotivationModule
    ) -> None:
        # Sembrar historial con confianza baja
        motivation.observe_confidence(0.3)
        motivation.observe_confidence(0.35)
        # Ahora una confianza mucho mayor genera reward
        delta = motivation.observe_confidence(0.85)
        assert delta > 0.0
        assert pytest.approx(delta, abs=0.001) == 0.3  # peso CURIOSITY

    def test_confidence_no_increase_no_reward(self, motivation: MotivationModule) -> None:
        motivation.observe_confidence(0.7)
        motivation.observe_confidence(0.7)
        # Misma confianza → no hay reward
        delta = motivation.observe_confidence(0.7)
        assert delta == 0.0


# ---------------------------------------------------------------------------
# Driver: reutilización de cápsulas
# ---------------------------------------------------------------------------


class TestCapsuleReuseDriver:
    def test_reward_capsule_use(self, motivation: MotivationModule) -> None:
        delta = motivation.reward_capsule_use("test-capsule-id")
        assert delta > 0.0
        assert pytest.approx(delta, abs=0.001) == 0.4  # peso CAPSULE_REUSE

    def test_reward_capsule_use_with_monologue_id(self, motivation: MotivationModule) -> None:
        delta = motivation.reward_capsule_use("cap-1", monologue_id="mono-1")
        assert delta > 0.0
        # Debe quedar registrado en DB
        recent = motivation.recent_rewards(limit=5)
        assert any(r["monologue_id"] == "mono-1" for r in recent)

    def test_capsule_reuse_calls_procedural_mark_used(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, tmp_path / "caps")
        rec = pm.store(name="Test", version="1.0.0", description="", content={})

        mm = MotivationModule(db_path=db_path, procedural=pm)
        assert pm.get(rec.id).uses == 0

        mm.reward_capsule_use(rec.id)
        assert pm.get(rec.id).uses == 1


# ---------------------------------------------------------------------------
# Driver: satisfacción del usuario (heurística)
# ---------------------------------------------------------------------------


class TestUserSatisfactionDriver:
    def test_negative_signal_penalizes(self, motivation: MotivationModule) -> None:
        delta = motivation.observe_user_input("no, eso está mal")
        assert delta < 0.0
        assert pytest.approx(delta, abs=0.001) == -0.5

    def test_neutral_input_no_immediate_reward(self, motivation: MotivationModule) -> None:
        # Primer input neutro: aún no hay racha completa
        delta = motivation.observe_user_input("cuéntame más")
        assert delta == 0.0

    def test_streak_complete_gives_reward(self, motivation: MotivationModule) -> None:
        # Window = 3 por defecto
        motivation.observe_user_input("hola")
        motivation.observe_user_input("gracias")
        delta = motivation.observe_user_input("perfecto")
        assert delta > 0.0
        assert pytest.approx(delta, abs=0.001) == 0.3

    def test_negative_resets_streak(self, motivation: MotivationModule) -> None:
        motivation.observe_user_input("hola")
        motivation.observe_user_input("gracias")
        # Señal negativa rompe la racha
        motivation.observe_user_input("no, mal")
        # Ahora necesitamos 3 turnos neutros de nuevo
        d1 = motivation.observe_user_input("ok")
        d2 = motivation.observe_user_input("sigue")
        d3 = motivation.observe_user_input("gracias")
        assert d1 == 0.0
        assert d2 == 0.0
        assert d3 > 0.0  # racha recién completada


# ---------------------------------------------------------------------------
# Persistencia + agregados
# ---------------------------------------------------------------------------


class TestMotivationPersistence:
    def test_total_reward_accumulates(self, motivation: MotivationModule) -> None:
        # Forzar rewards
        motivation.reward_capsule_use("cap-1")  # +0.4
        motivation.observe_user_input("eso está mal")  # -0.5
        total = motivation.total_reward()
        assert pytest.approx(total, abs=0.001) == -0.1

    def test_recent_rewards_returns_logged(self, motivation: MotivationModule) -> None:
        motivation.reward_capsule_use("cap-1")
        recent = motivation.recent_rewards(limit=5)
        assert len(recent) == 1
        assert recent[0]["driver"] == RewardDriver.CAPSULE_REUSE.value

    def test_rewards_by_driver(self, motivation: MotivationModule) -> None:
        motivation.reward_capsule_use("cap-1")  # +0.4
        motivation.reward_capsule_use("cap-2")  # +0.4
        motivation.observe_user_input("eso es incorrecto")  # -0.5
        agg = motivation.rewards_by_driver()
        assert agg[RewardDriver.CAPSULE_REUSE.value]["count"] == 2
        assert pytest.approx(agg[RewardDriver.CAPSULE_REUSE.value]["total_delta"], abs=0.001) == 0.8
        assert agg[RewardDriver.USER_SATISFACTION.value]["count"] == 1

    def test_stats(self, motivation: MotivationModule) -> None:
        motivation.observe_confidence(0.5)
        s = motivation.stats()
        assert s["module"] == "motivation"
        assert "session_total_reward" in s
        assert s["confidence_window_size"] == 1
        assert s["satisfaction_window"] == 3


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


class TestMotivationRobustness:
    def test_reward_capsule_use_without_procedural(self, motivation: MotivationModule) -> None:
        # procedural=None → no debe romper
        delta = motivation.reward_capsule_use("nonexistent")
        assert delta > 0.0

    def test_persistence_across_instances(self, db_path: Path) -> None:
        mm1 = MotivationModule(db_path=db_path, procedural=None)
        mm1.reward_capsule_use("cap-1")
        mm1_total = mm1.total_reward()
        del mm1

        # Nueva instancia con mismo DB debe ver los rewards persistidos
        mm2 = MotivationModule(db_path=db_path, procedural=None)
        recent = mm2.recent_rewards(limit=5)
        assert len(recent) == 1
        # session_total_reward NO persiste (es por sesión)
        assert mm2.total_reward() == 0.0
        # Pero podemos recuperar el total del último evento persistido
        assert pytest.approx(recent[0]["total"], abs=0.001) == mm1_total
