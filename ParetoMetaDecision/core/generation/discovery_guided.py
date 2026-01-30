# core/generation/discovery_guided.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class GuidedDiscoveryConfig:
    seed: int = 0
    max_candidates: int = 30
    top_k: int = 10
    mutation_rate: float = 1.0        # 1 mutación por candidato (no usado como prob; reservado)
    keep_horizon: bool = False
    p_lift_to_compound: float = 0.35  # si base es atómico, prob de convertirlo a AND/OR con otro átomo
    max_resample: int = 8             # re-muestreo para evitar AND(X,X)


class GuidedDiscoveryGenerator:
    """
    Discovery guiado: genera nuevos params dentro del vocabulario actual,
    mutando levemente los mejores params ya evaluados.
    NO introduce nuevos operadores ni mayor profundidad.
    Compatible con params_to_ast:
      - compuesto: {"policy":"AND"/"OR","left":{...},"right":{...}, "horizon":h}
      - atómico:   {"policy": "...", "k":..., "theta":..., "horizon":h}
    """
    def __init__(self, search_space: Dict[str, List[Any]], cfg: GuidedDiscoveryConfig):
        self.ss = search_space
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)

    def generate(self, *, best_params: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        if not best_params:
            return

        top = best_params[: max(1, self.cfg.top_k)]
        emitted = 0

        while emitted < self.cfg.max_candidates:
            base = self._deepish_copy(self.rng.choice(top))

            # Mutación 1: cambiar horizon (contexto), opcional
            if not self.cfg.keep_horizon and "horizon" in self.ss:
                base["horizon"] = self.rng.choice(self.ss["horizon"])

            # Normaliza el shape del compuesto si fuese necesario
            base = self._normalize_compound_shape(base)

            # Si es atómico, a veces lo "elevamos" a compuesto (sigue siendo vocabulario inicial)
            if base.get("policy") in ("absorption", "order_imbalance"):
                if self.rng.random() < self.cfg.p_lift_to_compound:
                    base = self._lift_atom_to_compound(base)

            # Mutación 2: pequeña alteración dentro del vocabulario actual
            cand = self._mutate_within_vocab(base)

            # Evita degenerados AND(X,X)/OR(X,X)
            if self._is_degenerate_compound(cand):
                # intenta corregirlo re-muestreando un lado pocas veces
                cand = self._repair_degenerate(cand)
                if self._is_degenerate_compound(cand):
                    continue

            yield cand
            emitted += 1

    # -------------------------
    # Mutaciones
    # -------------------------
    def _mutate_within_vocab(self, p: Dict[str, Any]) -> Dict[str, Any]:
        # Caso atómico
        if p.get("policy") in ("absorption", "order_imbalance"):
            return self._mutate_atom(p)

        # Caso compuesto
        if p.get("policy") in ("AND", "OR") and isinstance(p.get("left"), dict) and isinstance(p.get("right"), dict):
            choice = self.rng.choice(["op", "left", "right"])
            if choice == "op":
                p["policy"] = self.rng.choice(self.ss.get("compose_ops", ["AND", "OR"]))
                return p

            side = choice  # left/right
            # mutar ese lado (si ya es átomo, muta sus params; si no, reemplaza por átomo)
            if isinstance(p.get(side), dict) and p[side].get("policy") in ("absorption", "order_imbalance"):
                p[side] = self._mutate_atom(dict(p[side]))
            else:
                p[side] = self._sample_atom_params()
            return p

        return p

    def _mutate_atom(self, p: Dict[str, Any]) -> Dict[str, Any]:
        pol = p.get("policy")
        if pol == "absorption":
            field = self.rng.choice(["k", "theta"])
            if field == "k":
                p["k"] = self.rng.choice(self.ss.get("absorption.k", [p.get("k", 2)]))
            else:
                p["theta"] = self.rng.choice(self.ss.get("absorption.theta", [p.get("theta", 0.02)]))
            return p

        if pol == "order_imbalance":
            field = self.rng.choice(["k", "theta"])
            if field == "k":
                p["k"] = self.rng.choice(self.ss.get("order_imbalance.k", [p.get("k", 2)]))
            else:
                p["theta"] = self.rng.choice(self.ss.get("order_imbalance.theta", [p.get("theta", 0.1)]))
            return p

        return p

    def _lift_atom_to_compound(self, atom_params: Dict[str, Any]) -> Dict[str, Any]:
        op = self.rng.choice(self.ss.get("compose_ops", ["AND", "OR"]))
        other = self._sample_atom_params()
        # horizon fuera del AST
        horizon = atom_params.get("horizon")
        left = {k: v for k, v in atom_params.items() if k != "horizon"}
        cand = {"policy": op, "left": left, "right": other}
        if horizon is not None:
            cand["horizon"] = horizon
        return cand

    # -------------------------
    # Helpers / normalización
    # -------------------------
    def _sample_atom_params(self) -> Dict[str, Any]:
        pol = self.rng.choice(self.ss.get("rules", ["absorption"]))
        if pol == "absorption":
            return {
                "policy": "absorption",
                "k": self.rng.choice(self.ss.get("absorption.k", [2])),
                "theta": self.rng.choice(self.ss.get("absorption.theta", [0.02])),
            }
        return {
            "policy": "order_imbalance",
            "k": self.rng.choice(self.ss.get("order_imbalance.k", [2])),
            "theta": self.rng.choice(self.ss.get("order_imbalance.theta", [0.1])),
        }

    def _normalize_compound_shape(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        Si viene en formato plano left./right. (por compat), lo convierte a left/right dict.
        Si ya es correcto, no hace nada.
        """
        if p.get("policy") not in ("AND", "OR"):
            return p
        if isinstance(p.get("left"), dict) and isinstance(p.get("right"), dict):
            return p

        # Compat: left.<k> / right.<k>
        left = {k.replace("left.", ""): v for k, v in p.items() if k.startswith("left.")}
        right = {k.replace("right.", ""): v for k, v in p.items() if k.startswith("right.")}

        if left and right:
            horizon = p.get("horizon")
            out = {"policy": p["policy"], "left": left, "right": right}
            if horizon is not None:
                out["horizon"] = horizon
            return out

        return p

    def _is_degenerate_compound(self, p: Dict[str, Any]) -> bool:
        if p.get("policy") not in ("AND", "OR"):
            return False
        left = p.get("left")
        right = p.get("right")
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        return left == right

    def _repair_degenerate(self, p: Dict[str, Any]) -> Dict[str, Any]:
        if p.get("policy") not in ("AND", "OR") or not isinstance(p.get("left"), dict) or not isinstance(p.get("right"), dict):
            return p

        # re-muestrea un lado para que sea distinto
        side = self.rng.choice(["left", "right"])
        for _ in range(self.cfg.max_resample):
            cand = self._sample_atom_params()
            if cand != p[side]:
                p[side] = cand
                break
        return p

    def _deepish_copy(self, p: Dict[str, Any]) -> Dict[str, Any]:
        # copia suficiente para no compartir dicts internos
        out = dict(p)
        if isinstance(out.get("left"), dict):
            out["left"] = dict(out["left"])
        if isinstance(out.get("right"), dict):
            out["right"] = dict(out["right"])
        return out
