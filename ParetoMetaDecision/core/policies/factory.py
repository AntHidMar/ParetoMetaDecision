# core/policies/factory.py
from __future__ import annotations
from typing import Any, Dict

Params = Dict[str, Any]


def _require_keys(d: dict, keys: list[str], ctx: str):
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{ctx}: missing keys {missing}")


def build_policy(*args, **kwargs):
    raise RuntimeError(
        "core.policies.factory is deprecated. "
        "Policies must be built in the domain plugin (e.g., plugins/investment)."
    )
