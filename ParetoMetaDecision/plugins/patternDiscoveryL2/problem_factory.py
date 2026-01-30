# plugins/patternDiscoveryL2/problem_factory.py
from __future__ import annotations

from typing import Any, Dict, Tuple, Optional

from core.problem.base import Problem
from core.utils.yaml_io import load_yaml

# Reutilizamos el loader de inversionL2 (single source of truth)
from plugins.inversionL2.data_loader import load_dataset  # <- ajusta si tu función se llama distinto

from plugins.patternDiscoveryL2.evaluator import make_evaluator


def _load_dataset_from_yaml(domain: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    
    print("patternDiscoveryL2 -- _load_dataset_from_yaml - ")
    
    print("DBG[factory] domain.data =", domain.get("data"))

    """
    Carga dataset usando el dataset.yaml apuntado por domain.yaml.
    Mantiene una sola fuente de verdad: plugins/inversionL2/data_loader.py
    """
    dataset_yaml_path = domain.get("data", {}).get("dataset_yaml")
    if not dataset_yaml_path:
        raise KeyError("domain.data.dataset_yaml missing")

    dataset_cfg = load_yaml(dataset_yaml_path)

    # Contrato esperado: load_dataset(dataset_cfg) -> (dataset, dataset_desc)
    out = load_dataset(dataset_cfg)

    # Soporta ambas firmas:
    #  - devuelve dataset
    #  - devuelve (dataset, dataset_desc)
    if isinstance(out, tuple) and len(out) == 2:
        dataset, dataset_desc = out
    else:
        dataset, dataset_desc = out, {"dataset_yaml": dataset_yaml_path}

    # Normaliza para que evaluator reciba dict con df
    if isinstance(dataset, dict) and "df" in dataset:
        pass
    else:
        dataset = {"df": dataset}

    return dataset, dataset_desc


def make_problem(cfg: Dict[str, Any]) -> Problem:
    """
    Factory compatible con core.problem.loader:
    cfg == domain.yaml (dict).
    """
    domain = cfg["domain_cfg"]
    
    dataset, dataset_desc = _load_dataset_from_yaml(domain)

    evaluator = make_evaluator(domain=domain, dataset=dataset, dataset_desc=dataset_desc)

    def _context(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = dict(domain.get("context", {}) or {})
        ctx["problem_id"] = domain.get("problem_id", "patternDiscoveryL2")
        if params:
            ctx["horizon"] = params.get("horizon", ctx.get("horizon"))
            ctx["policy_root"] = params.get("policy") or params.get("rules")
        
        return ctx

    def _evaluate(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return evaluator.evaluate(params=params, context=context)

    return Problem(
        name=domain.get("name", "Pattern Discovery L2"),
        evaluate=_evaluate,
        context=_context,
    )
