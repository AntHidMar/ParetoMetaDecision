# core/generation/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Protocol


@dataclass(frozen=True)
class GenerationBudget:
    max_candidates: Optional[int] = None  # None => sin límite


class CandidateGenerator(Protocol):
    """
    Genera candidatos de lenguaje (AST) para ser evaluados.
    Debe devolver ASTs ya canónicos (o al menos estables) para que dedup funcione.
    """
    def generate(
        self,
        *,
        problem: Any,
        budget: GenerationBudget,
    ) -> Iterable[Any]:
        ...
