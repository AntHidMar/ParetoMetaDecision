from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

from core.decision_language.ast import AstNode


@dataclass(frozen=True)
class LanguageConstraints:
    max_depth: int = 2
    max_size: int = 7


def interpretability_metrics(ast: AstNode) -> Dict[str, Any]:
    return {
        "ast_size": int(ast.size()),
        "ast_depth": int(ast.depth()),
    }


def validate_language(ast: AstNode, c: LanguageConstraints) -> List[str]:
    """
    Soft validation (MapA7): no bloquea por defecto.
    Devuelve lista de violaciones (vacía => OK).
    """
    v: List[str] = []
    s = int(ast.size())
    d = int(ast.depth())

    if d > c.max_depth:
        v.append(f"depth>{c.max_depth} (got {d})")
    if s > c.max_size:
        v.append(f"size>{c.max_size} (got {s})")

    return v
