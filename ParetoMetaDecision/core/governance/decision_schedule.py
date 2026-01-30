# core/governance/decision_schedule.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import numpy as np
import pandas as pd

DecisionMode = Literal["sample", "hold"]


@dataclass(frozen=True)
class TimeGridSchedule:
    seconds: int
    mode: DecisionMode = "hold"


class DecisionScheduler:
    """
    gate[t]=True cuando se permite decidir (actualizar señal).
    Implementación mínima: time_grid por timestamp.
    """

    def __init__(self, schedule: TimeGridSchedule):
        if schedule.seconds <= 0:
            raise ValueError("schedule.seconds must be > 0")
        self.schedule = schedule

    def gate(self, timestamps: List[pd.Timestamp]) -> np.ndarray:
        if not timestamps:
            return np.zeros(0, dtype=bool)

        ts = pd.to_datetime(pd.Series(timestamps))
        s = (ts.astype("int64") // 1_000_000_000).to_numpy()

        bucket = s // int(self.schedule.seconds)

        gate = np.zeros(len(bucket), dtype=bool)
        gate[0] = True
        if len(bucket) > 1:
            gate[1:] = bucket[1:] != bucket[:-1]
        return gate


def apply_decision_mode_tri(raw_signal: np.ndarray, gate: np.ndarray, mode: DecisionMode) -> np.ndarray:
    """
    raw_signal: float tri {-1,0,+1} por snapshot
    gate: bool por snapshot
    mode:
      - sample: solo emite señal en gate=True; resto 0
      - hold: actualiza estado en gate=True; mantiene último estado fuera de gate
    """
    raw = np.asarray(raw_signal, dtype=float)
    g = np.asarray(gate, dtype=bool)
    if len(raw) != len(g):
        raise ValueError("raw_signal and gate must have same length")

    if mode == "sample":
        out = np.zeros_like(raw)
        out[g] = raw[g]
        return out

    if mode == "hold":
        out = np.zeros_like(raw)
        last = 0.0
        for i in range(len(raw)):
            if g[i]:
                last = float(raw[i])
            out[i] = last
        return out

    raise ValueError(f"Unknown mode: {mode}")
