from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class FlatProductConfig:
    max_candidates: int = 300
    # claves que NO deben formar parte del producto (meta-params)
    ignore_keys: Tuple[str, ...] = ("horizon",)


def flat_product_candidates(search_space: Dict[str, List[Any]], cfg: FlatProductConfig) -> Iterable[Dict[str, Any]]:
    """
    Genera combinaciones cartesianas para un search_space plano:
      {"policy":[...], "theta":[...], ...}
    No asume nada de "rules", "left/right", etc.
    """
    keys = [k for k in search_space.keys() if k not in cfg.ignore_keys]
    if not keys:
        return  # no candidates

    values = []
    for k in keys:
        v = search_space.get(k)
        if not isinstance(v, list) or len(v) == 0:
            return  # search_space inválido => 0 candidates
        values.append(v)

    n = 0
    for combo in product(*values):
        yield dict(zip(keys, combo))
        n += 1
        if n >= cfg.max_candidates:
            break
