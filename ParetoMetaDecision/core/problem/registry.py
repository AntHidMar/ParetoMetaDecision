# core/problem/registry.py
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from core.problem.base import Problem

def _import_callable(path: str) -> Callable[..., Any]:
    """
    path: "module.submodule:callable_name"
    """
    if ":" not in path:
        raise ValueError(f"Factory path must be 'module:callable'. Got: {path}")
    mod_name, fn_name = path.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Factory '{fn_name}' not found/callable in module '{mod_name}'")
    return fn

@dataclass
class ProblemRegistry:
    """
    Registro mínimo: resuelve un ProblemSpec -> Problem ejecutable
    sin que el core conozca el dominio.
    """
    specs: Dict[str, Any]  # normalmente Dict[str, ProblemSpec]

    def get_spec(self, problem_id: str) -> Any:
        if problem_id not in self.specs:
            raise KeyError(f"Unknown problem_id: {problem_id}. Available: {list(self.specs.keys())}")
        return self.specs[problem_id]

    def build(self, problem_id: str, *, config: Optional[Dict[str, Any]] = None) -> Problem:
        spec = self.get_spec(problem_id)

        # Merge config (override default_config)
        merged = dict(getattr(spec, "default_config", {}) or {})
        if config:
            merged.update(config)

        factory_path = getattr(spec, "factory")
        factory = _import_callable(factory_path)

        # La factory debe devolver core.problem.base.Problem (tu dataclass)
        problem = factory(merged)

        if not isinstance(problem, Problem):
            raise TypeError(
                f"Factory '{factory_path}' must return core.problem.base.Problem. Got: {type(problem)}"
            )

        return problem
