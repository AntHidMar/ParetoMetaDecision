# core/problem/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

Params = Dict[str, Any]
Metrics = Dict[str, Any]
Context = Dict[str, Any]

@dataclass(frozen=True)
class Problem:
    """
    Contrato transversal mínimo:
    - El core solo conoce que puede evaluar un candidato (params dict) -> métricas dict.
    - Ningún detalle de dominio aquí.
    """
    name: str
    evaluate: Callable[[Params, Metrics], Context]
    context: Callable[[], Dict[str, Any]] | Dict[str, Any]
