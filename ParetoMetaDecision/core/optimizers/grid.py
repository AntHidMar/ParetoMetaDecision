# core/optimizers/grid.py
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Iterator, List
import json


Params = Dict[str, Any]


@dataclass
class GridSearch:
    search_space: Dict[str, List[Any]]
    horizons: List[int]
    # combinación lógica
    enable_compose: bool = True
    max_compose_depth: int = 1  # 1 = AND/OR entre dos reglas simples

    def _simple_rules(self) -> List[Params]:
        rules = self.search_space.get("rules", [])
        out: List[Params] = []

        global_h = self.search_space.get("horizon")  # <-- fuera

        for rule in rules:
            keys = [k for k in self.search_space.keys() if k.startswith(f"{rule}.")]
            if not keys:
                base = {"policy": rule}
                if global_h:
                    for h in global_h:
                        p = dict(base)
                        p["horizon"] = h
                        out.append(p)
                else:
                    out.append(base)
                continue

            values = [self.search_space[k] for k in keys]
            for combo in product(*values):
                p = {"policy": rule}
                for k, v in zip(keys, combo):
                    p[k.split(".", 1)[1]] = v  # quita prefix "<rule>."

                # <-- aquí va EXACTAMENTE la línea de k por defecto
                if p.get("policy") == "absorption":
                    p.setdefault("k", 2)

                if global_h:
                    for h in global_h:
                        pp = dict(p)
                        pp["horizon"] = h
                        out.append(pp)
                else:
                    out.append(p)

        return out

    def _simple_rules_old(self) -> List[Params]:
        """
        Produce reglas simples: cada una es un dict con policy=<name> y sus hiperparámetros.
        Estructura esperada en search_space:
          - "rules": list[str]  (p.ej. ["absorption","imbalance"])
          - para cada regla, un namespace: "<rule>.<param>": list
            p.ej. "absorption.theta": [0.01,0.02], "absorption.k":[2,3]
        """
        rules = self.search_space.get("rules", [])
        out: List[Params] = []

        for rule in rules:
            # recoge hiperparámetros de esa regla
            keys = [k for k in self.search_space.keys() if k.startswith(f"{rule}.")]
            if not keys:
                out.append({"policy": rule})
                continue

            values = [self.search_space[k] for k in keys]
            for combo in product(*values):
                p = {"policy": rule}
                for k, v in zip(keys, combo):
                    p[k.split(".", 1)[1]] = v  # quita prefix "<rule>."

                    # dentro del loop donde creas p para cada combo de una regla
                    global_h = self.search_space.get("horizon")
                    if global_h is None:
                        out.append(p)
                    else:
                        for h in global_h:
                            pp = dict(p)
                            pp["horizon"] = h
                            out.append(pp)
                if p.get("policy") == "absorption":
                    p.setdefault("k", 2)
                out.append(p)

        return out

    def _compose(self, base: List[Params]) -> List[Params]:
        """
        Crea AND/OR sobre reglas base.
        depth=1: AND/OR(left=simple, right=simple)
        """
        if not self.enable_compose or self.max_compose_depth < 1:
            return []

        composed: List[Params] = []
        ops = self.search_space.get("compose_ops", ["AND", "OR"])

        for op in ops:
            for i, left in enumerate(base):
                for j, right in enumerate(base):
                    if j < i:              # evita permutaciones duplicadas (A,B) vs (B,A)
                        continue
                    if left == right:      # evita AND/OR con la misma regla
                        continue
                    if left.get("horizon") != right.get("horizon"):
                        continue
                    h = left.get("horizon")
                    composed.append({"policy": op, "left": left, "right": right, "horizon": h})
                    
        return composed

    def generate(self):
        base = self._simple_rules()
        composed = self._compose(base) or []

        all_params = list(base) + list(composed)

        seen = set()
        for p in all_params:
            # firma estable: ordena keys y serializa
            key = json.dumps(p, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            yield p

    def generate_old(self):
        base = self._simple_rules()
        composed = self._compose(base) or []

        all_params = list(base) + list(composed)

        horizons = self.search_space.get("horizon")
        seen = set()

        for p in all_params:
            if horizons:
                for h in horizons:
                    pp = dict(p)
                    pp["horizon"] = h
                    key = json.dumps(pp, sort_keys=True, ensure_ascii=False)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield pp
            else:
                key = json.dumps(p, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    continue
                seen.add(key)
                yield p