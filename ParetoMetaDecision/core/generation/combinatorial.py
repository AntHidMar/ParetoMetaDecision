# core/generation/combinatorial.py
from __future__ import annotations

from typing import Any, Iterable

from core.generation.base import CandidateGenerator, GenerationBudget


class CombinatorialGenerator(CandidateGenerator):
    """
    Wrapper del generador combinatorio existente (p.ej. GridSearch).
    No reinventa la lógica de combinaciones: solo estandariza la salida y aplica budget.
    """
    def __init__(self, backend: Any):
        # backend debe exponer .generate() -> Iterable[params: dict]
        self.backend = backend

    def generate(self, *, problem: Any, budget: GenerationBudget) -> Iterable[dict]:
        emitted = 0
        for params in self.backend.generate():
            yield params
            emitted += 1
            if budget.max_candidates is not None and emitted >= budget.max_candidates:
                return
