from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

@dataclass(frozen=True)
class OptimizerSpec:
    id: str
    params: Dict[str, Any]

def get_optimizer_spec(domain: Dict[str, Any]) -> OptimizerSpec:
    cfg = (domain.get("optimizer") or {})
    oid = str(cfg.get("id", "grid")).lower()
    params = dict(cfg.get("params") or {})
    return OptimizerSpec(id=oid, params=params)
