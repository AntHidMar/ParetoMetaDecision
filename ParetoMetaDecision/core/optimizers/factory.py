# core/optimizers/factory.py
from __future__ import annotations

from typing import Any, Dict

# Importa los optimizadores implementados (aunque algunos sean stubs al principio)
from core.optimizers.grid import GridSearch
from core.optimizers.random import RandomSearch
from core.optimizers.nsga2 import NSGA2Optimizer


def build_candidate_generator(cfg: Dict[str, Any], search_space: Dict[str, Any]):
    """
    Factory MapA-9:
    - Selección del optimizador por YAML (cfg["optimizer"]["type"])
    - El optimizador SOLO genera candidatos (no evalúa).
    """
    opt_cfg = (cfg or {}).get("optimizer", {}) or {}
    opt_type = (opt_cfg.get("id") or opt_cfg.get("type") or "grid").lower()

    max_evals = int(opt_cfg.get("max_evals", 500))
    params = opt_cfg.get("params", {}) or {}
    seed = int(opt_cfg.get("seed", params.get("seed", 0)))
    
    if opt_type == "grid":
        return GridSearch(
            search_space=search_space,
            horizons=search_space.get("horizon"),
            enable_compose=True,
            max_compose_depth=int(opt_cfg.get("max_compose_depth", 1)),
        )

    if opt_type == "random":
        return RandomSearch(
            search_space=search_space,
            max_evals=max_evals,
            seed=seed,
        )

    if opt_type == "nsga2":
        print("DEBUG search_space keys:", getattr(search_space, "__dict__", search_space).keys() if search_space else None)
        print("DEBUG flat_rules len:", len(getattr(search_space, "flat_rules", []) or []))
        print("DEBUG flat_rules:", getattr(search_space, "flat_rules", None))

        return NSGA2Optimizer(
            search_space=search_space,
            max_evals=max_evals,
            seed=seed,
            pop_size=int(params.get("pop_size", 80)),
            offspring_size=int(params.get("offspring_size", 80)),
            tournament_k=int(params.get("tournament_k", 2)),
            crossover_rate=float(params.get("crossover_rate", 0.9)),
            mutation_rate=float(params.get("mutation_rate", 0.2)),
            max_depth=int(params.get("max_depth", 4)),
            max_nodes=int(params.get("max_nodes", 15)),
        )

    raise ValueError(f"Unknown optimizer type='{opt_type}'. Expected: grid | random | nsga2")
