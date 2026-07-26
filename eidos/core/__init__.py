"""Core cognitivo de EIDOS.

Componentes:
- engine:       orquesta monólogo → acción → respuesta.
- monologue:    generador de CoT estructurado (JSON schema forzado).
- router:       decide la ruta de acción tras el monólogo.
- motivation:   reward signal interno (Fase 1.3).
- consolidator: loop de consolidación en background (Fase 1.3).
"""

from eidos.core.consolidator import Consolidator
from eidos.core.engine import EidosCore, Response
from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.motivation import MotivationModule, RewardDriver
from eidos.core.router import ActionRouter, Route, RouteType

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
]
