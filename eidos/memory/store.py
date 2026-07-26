"""Fachada unificada de las 5 capas de memoria cognitiva.

MemoryStore inicializa y coordina las 5 capas. Es la única entrada
que el EidosCore necesita — internamente delega a cada capa.

Uso:
    store = MemoryStore.from_config(config, project_root)
    store.sensory.store("user_input", "hola")
    store.episodic.search("hola")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eidos.memory.base import MemoryLayer
from eidos.memory.episodic import EpisodicMemory
from eidos.memory.metacognitive import MetacognitiveMemory
from eidos.memory.procedural import ProceduralMemory
from eidos.memory.semantic import SemanticMemory
from eidos.memory.sensory import SensoryMemory
from eidos.utils.logging import get_logger
from eidos.utils.persistence import apply_migrations

logger = get_logger(__name__)


class MemoryStore:
    """Coordina las 5 capas cognitivas. Singleton por proceso EIDOS."""

    def __init__(
        self,
        db_path: Path,
        migrations_dir: Path,
        sensory: SensoryMemory,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        procedural: ProceduralMemory,
        metacognitive: MetacognitiveMemory,
    ) -> None:
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.sensory = sensory
        self.episodic = episodic
        self.semantic = semantic
        self.procedural = procedural
        self.metacognitive = metacognitive

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        project_root: Path,
        embedder: Any = None,
    ) -> "MemoryStore":
        """Construye el MemoryStore aplicando migraciones primero.

        Args:
            config: dict de config completo.
            project_root: raíz del proyecto.
            embedder: opcional, inyecta un EmbedderBackend (Fase 2) para la
                capa episódica. Si es None, usa stub_embed.
        """
        mem_cfg = config.get("memory", {})
        db_path = project_root / mem_cfg.get("episodic", {}).get("db_path", "data/eidos.db")
        migrations_dir = project_root / "data/migrations"

        # 1. Aplicar migraciones (crea tablas + extensiones)
        n = apply_migrations(db_path, migrations_dir)
        logger.info("memory_migrations_applied", count=n)

        # 2. Instanciar capas
        sensory = SensoryMemory(
            db_path=db_path,
            window_size=int(mem_cfg.get("sensory", {}).get("window_size", 50)),
        )
        episodic = EpisodicMemory(
            db_path=db_path,
            embedding_dim=int(mem_cfg.get("episodic", {}).get("embedding_dim", 256)),
            max_events=int(mem_cfg.get("episodic", {}).get("max_events", 10000)),
            embedder=embedder,
        )
        semantic = SemanticMemory(
            graph_path=project_root / mem_cfg.get("semantic", {}).get("graph_path", "data/graph.json"),
        )
        procedural = ProceduralMemory(
            db_path=db_path,
            capsules_dir=project_root / mem_cfg.get("procedural", {}).get("capsules_dir", "data/capsules"),
            default_ttl_days=int(mem_cfg.get("procedural", {}).get("default_ttl_days", 7)),
        )
        metacognitive = MetacognitiveMemory(db_path=db_path)

        return cls(
            db_path=db_path,
            migrations_dir=migrations_dir,
            sensory=sensory,
            episodic=episodic,
            semantic=semantic,
            procedural=procedural,
            metacognitive=metacognitive,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "sensory": self.sensory.stats(),
            "episodic": self.episodic.stats(),
            "semantic": self.semantic.stats(),
            "procedural": self.procedural.stats(),
            "metacognitive": self.metacognitive.stats(),
        }

    def all_layers(self) -> list[MemoryLayer]:
        return [self.sensory, self.episodic, self.semantic, self.procedural, self.metacognitive]


__all__ = ["MemoryStore"]
