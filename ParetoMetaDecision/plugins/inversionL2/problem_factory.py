# plugins/inversionL2/problem_factory.py

from __future__ import annotations

from typing import Any, Dict
from core.problem.base import Problem, Params, Metrics

from core.utils.yaml_io import load_yaml
from plugins.inversionL2.data_loader import load_dataset
from plugins.inversionL2.evaluator import make_evaluator

def make_problem(cfg: Dict[str, Any]) -> Problem:
    """
    cfg se obtiene desde domain.yaml (y overrides).
    El dataset se describe en dataset.yaml.
    """

    domain = cfg.get("domain_cfg") or cfg.get("domain")
    if domain is None:
        raise KeyError("cfg['domain_cfg'] missing")

    dataset_yaml = domain["data"]["dataset_yaml"]
    dataset_desc = load_yaml(dataset_yaml)
    dataset = load_dataset(dataset_desc)  # devuelve objeto/df/estructura plugin-owned

    # DEBUG dataset sanity (opt-in por YAML)
    if (domain.get("debug") or {}).get("dataset", False):
        try:
            df = dataset.get("df") if isinstance(dataset, dict) else getattr(dataset, "df", None)
            if df is not None:
                print("DBG[df] shape =", df.shape)
                print("DBG[df] fecha min/max =", df["fecha"].min(), df["fecha"].max())
                if "priceL1" in df.columns:
                    print("DBG[df] priceL1 std =", float(df["priceL1"].std()))
                if "priceL2" in df.columns:
                    print("DBG[df] priceL2 std =", float(df["priceL2"].std()))
        except Exception as e:
            print("DBG dataset sanity ERROR =", repr(e))

        
    # Build evaluator closure
    evaluator = make_evaluator(domain=domain, dataset=dataset, dataset_desc=dataset_desc)

    def _context(params: Params | None = None) -> Dict[str, Any]:
        # Contexto fuera del AST: horizon, dataset_id, regime, etc.
        horizons = domain.get("context", {}).get("horizons", [])
        default_h = horizons[0] if horizons else None
        horizon = (params or {}).get("horizon", default_h)

        # dataset_id plugin-owned (puede ser hash del yaml o contenido real)
        dataset_id = (
            dataset_desc.get("dataset_id")
            or (dataset.get("dataset_id") if isinstance(dataset, dict) else None)
            or f"{dataset_yaml}"
        )
        return {
            "problem_id": domain.get("problem_id", "inversionL2"),
            "dataset_id": dataset_id,
            "horizon": horizon,
            "regime": domain.get("context", {}).get("regime", "all"),
            "cost_model": domain.get("context", {}).get("cost_model", "none"),
            "audit_mode": str(((domain.get("audit") or {}).get("decision_events") or {}).get("mode", "off")).lower(),
        }

    def _evaluate(params: Params, context: Dict[str, Any] | None = None) -> Metrics:
        # Si el core te pasa ctx, úsalo. Si no, deriva uno por defecto.
        ctx = context or _context(params)

        m = evaluator.evaluate(params=params, context=ctx)

        if not isinstance(m, dict):
            raise TypeError("evaluator.evaluate() must return dict metrics")

        if getattr(_evaluate, "_dbg", 0) < 3:
            _evaluate._dbg = getattr(_evaluate, "_dbg", 0) + 1
            print("DBG params:", params)
            print("DBG metrics:", m)

        return m


    return Problem(name=domain.get("name", "inversionL2"), evaluate=_evaluate, context=_context)
