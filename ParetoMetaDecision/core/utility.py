# core/utility.py

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class UtilitySpec:
    lambda_cost: float = 0.0
    lambda_risk: float = 1.0
    lambda_frequency: float = 0.0   # ⬅️ AÑADIR

    
def compute_utility(
                        *,
                        profit: float,
                        risk: float,
                        frequency: float,
                        spec: UtilitySpec,
                    ) -> float:
    """
    Utility general (MapA 8–9):
    - maximiza profit
    - penaliza risk
    - incentiva frequency (evita abstención trivial)
    """
    eps = 1e-12
    # utilidad adimensional: reward/risk, y penaliza operar demasiado
    return float((profit / (risk + eps)) - spec.lambda_cost * frequency)

