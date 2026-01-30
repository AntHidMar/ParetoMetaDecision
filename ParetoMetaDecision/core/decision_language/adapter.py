# core/decision_language/adapter.py

from __future__ import annotations
from typing import Any, Dict, Tuple

from core.decision_language.ast import Atom, And, Or, AstNode

Params = Dict[str, Any]


def split_horizon(params: Params) -> Tuple[int, Params]:
    p = dict(params)
    h = int(p.pop("horizon", 0))
    return h, p

def ast_to_params(ast: AstNode, horizon: int) -> Params:
    """
    Serialize AST back to params dict and reattach horizon at the root.
    """
    d = ast.to_dict()
    d["horizon"] = int(horizon)
    return d

from core.decision_language.ast import Atom, And, Or

def _dict_rule_to_atom(rule_params: dict) -> Atom:
    policy = rule_params["policy"]
    atom_params = {k: v for k, v in rule_params.items() if k not in ("policy", "horizon")}
    return Atom(policy=policy, params=atom_params)

def _extract_rule_params(params: dict, rule: str) -> dict:
    # Soporta "<rule>.<param>" (si lo usas)
    out = {}
    prefix = f"{rule}."
    for k, v in params.items():
        if k.startswith(prefix):
            out[k[len(prefix):]] = v
    return out

def params_to_ast(params: dict):
    # ------------------------------------------------------------
    # (1) Formato compuesto del GridSearch actual: policy=AND/OR + left/right dict
    # ------------------------------------------------------------
    p = params.get("policy")
    if p in ("AND", "OR") and isinstance(params.get("left"), dict) and isinstance(params.get("right"), dict):
        left_atom = _dict_rule_to_atom(params["left"])
        right_atom = _dict_rule_to_atom(params["right"])
        return And(left_atom, right_atom) if p == "AND" else Or(left_atom, right_atom)

    # ------------------------------------------------------------
    # (2) Formato "policy tupla": policy=(r1,r2)  (parche de compatibilidad)
    # ------------------------------------------------------------
    if isinstance(p, (tuple, list)) and len(p) == 2 and all(isinstance(x, str) for x in p):
        r1, r2 = p[0], p[1]
        op = params.get("compose_op") or params.get("compose_ops") or "AND"
        if op not in ("AND", "OR"):
            raise TypeError(f"Unknown compose op: {op}")

        # Si vienen params con prefijo "<rule>.<param>"
        a1_params = _extract_rule_params(params, r1)
        a2_params = _extract_rule_params(params, r2)

        # Si no vienen prefijados, intentamos repartir desde keys planas (no ideal, pero evita crash)
        # Nota: si tus keys son theta/k planos, NO podemos saber cuál es de cuál; por eso preferimos prefijo.
        left_atom = Atom(policy=r1, params=a1_params)
        right_atom = Atom(policy=r2, params=a2_params)

        return And(left_atom, right_atom) if op == "AND" else Or(left_atom, right_atom)

    # ------------------------------------------------------------
    # (3) Caso simple
    # ------------------------------------------------------------
    if not isinstance(p, str):
        raise TypeError(f"params['policy'] must be str, got {type(p)}: {p}")

    atom_params = {k: v for k, v in params.items() if k not in ("policy", "horizon", "compose_op", "compose_ops", "rules", "left", "right")}
    return Atom(policy=p, params=atom_params)


