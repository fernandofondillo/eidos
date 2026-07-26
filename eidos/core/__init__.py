"""Core cognitivo de EIDOS.

Componentes:
- engine:       orquesta monólogo → acción → respuesta.
- monologue:    generador de CoT estructurado (JSON schema forzado).
- router:       decide la ruta de acción tras el monólogo.
- motivation:   reward signal interno (Fase 1.3).
- consolidator: loop de consolidación en background (Fase 1.3).
- sandbox:      ToolSandbox con defense-in-depth para código generado (Fase 3.1).
- forge:        CapsuleForge — génesis de cápsulas .eidos (Fase 3.2).
- evolution:    EvolutionLoop — detección de necesidad + autoevolución (Fase 3.3).
"""

from eidos.core.consolidator import Consolidator
from eidos.core.engine import EidosCore, Response
from eidos.core.evolution import EvolutionLoop
from eidos.core.forge import (
    CapsuleDraft,
    CapsuleForge,
    CapsuleOntology,
    CapsuleRule,
    CapsuleTone,
    CapsuleTool,
    ForgeBackend,
    ForgeDecision,
    LLMForgeBackend,
    StubForgeBackend,
)
from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.motivation import MotivationModule, RewardDriver
from eidos.core.router import ActionRouter, Route, RouteType
from eidos.core.sandbox import (
    SandboxError,
    SandboxResult,
    SandboxSecurityError,
    ToolSandbox,
    validate_ast,
)

__all__ = [
    "EidosCore",
    "Response",
    "Monologue",
    "MonologueGenerator",
    "ActionRouter",
    "Route",
    "RouteType",
    "MotivationModule",
    "RewardDriver",
    "Consolidator",
    "ToolSandbox",
    "SandboxResult",
    "SandboxError",
    "SandboxSecurityError",
    "validate_ast",
    "CapsuleForge",
    "CapsuleDraft",
    "CapsuleTool",
    "CapsuleRule",
    "CapsuleOntology",
    "CapsuleTone",
    "ForgeBackend",
    "StubForgeBackend",
    "LLMForgeBackend",
    "ForgeDecision",
    "EvolutionLoop",
]
