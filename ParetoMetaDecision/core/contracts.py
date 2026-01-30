# core/contracts.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import json

@dataclass(frozen=True)
class EvalMetrics:
    mean_return: float
    frequency: float
    win_rate: float
    n_long: int
    # extensible:
    extra: Dict[str, Any] = None

@dataclass(frozen=True)
class EvaluationRecord:
    params: Dict[str, Any]          # regla / configuración (después será AST)
    horizon: int
    metrics: EvalMetrics
    utility: float                 # MapA 5: utilidad de decisión
    meta: Dict[str, Any]           # trazabilidad (version, dataset, etc.)

    @property
    def params_json(self) -> str:
        return json.dumps(self.params, sort_keys=True, ensure_ascii=False)
