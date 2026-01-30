# core/problem/loader.py
from __future__ import annotations
from typing import Any, Dict, Optional

from core.utils.yaml_io import load_yaml
from core.utils.imports import import_from_string

def load_problem_from_domain_yaml(domain_yaml: str, overrides: Optional[Dict[str, Any]] = None):
    domain_cfg = load_yaml(domain_yaml)
    factory_ref = domain_cfg.get("factory")
    if not factory_ref:
        raise KeyError(f"domain.yaml missing 'factory': {domain_yaml}")

    factory_fn = import_from_string(factory_ref)

    cfg: Dict[str, Any] = {"domain_yaml": domain_yaml}
    if overrides:
        cfg.update(overrides)

    return factory_fn({"domain_cfg": domain_cfg, "domain_yaml": domain_yaml})


