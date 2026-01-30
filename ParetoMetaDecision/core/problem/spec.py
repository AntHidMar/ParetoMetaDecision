# core/problem/spec.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

ObjectiveDirection = Literal["max", "min"]

@dataclass(frozen=True)
class ObjectiveSpec:
    """Especificación de un objetivo (nombre + dirección)."""
    name: str
    direction: ObjectiveDirection = "max"

@dataclass(frozen=True)
class ContextFieldSpec:
    """
    Campo permitido en el contexto (fuera del AST).
    Esto ayuda a consolidar generalidad y estabilidad de context_key.
    """
    name: str
    required: bool = False
    default: Any = None
    # Nota: mantenlo simple para no introducir dependencias de validación.

@dataclass(frozen=True)
class ProblemSpec:
    """
    Especificación declarativa de un problema.
    - No contiene lógica de dominio.
    - Permite al core cargar/instanciar el Problem desde plugins.
    """
    problem_id: str                 # ej. "investment"
    name: str                       # nombre humano
    factory: str                    # "plugins.investment.problem_factory:make_problem"

    # Metadatos de evaluación
    objectives: List[ObjectiveSpec] = field(default_factory=list)

    # Esquema mínimo de contexto (horizon, dataset_id, regime, etc.)
    context_fields: List[ContextFieldSpec] = field(default_factory=list)

    # Config por defecto del problema (input para factory)
    default_config: Dict[str, Any] = field(default_factory=dict)
