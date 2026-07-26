"""Capa de memoria cognitiva — las 5 capas + fachada MemoryStore.

Capas:
- sensory:        contexto inmediato (deque + SQLite)
- episodic:       memoria vectorial (sqlite-vec / bruteforce fallback)
- semantic:       grafo de conocimiento (networkx -> JSON)
- procedural:     cápsulas y herramientas (.eidos + SQLite index)
- metacognitive:  índice de monólogos pasados (SQLite)
"""

from eidos.memory.base import MemoryLayer
from eidos.memory.episodic import EMBEDDING_DIM, EpisodicMemory, stub_embed
from eidos.memory.metacognitive import MetacognitiveMemory
from eidos.memory.procedural import CapsuleRecord, ProceduralMemory
from eidos.memory.semantic import SemanticMemory
from eidos.memory.sensory import SensoryMemory
from eidos.memory.store import MemoryStore

__all__ = [
    "MemoryLayer",
    "MemoryStore",
    "SensoryMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "ProceduralMemory",
    "MetacognitiveMemory",
    "CapsuleRecord",
    "stub_embed",
    "EMBEDDING_DIM",
]
