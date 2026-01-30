# core/context.py
from __future__ import annotations
from typing import Any, Dict
from core.artifacts.hash import stable_json_dumps, sha256_str

Context = Dict[str, Any]

def context_key(context: Context) -> str:
    return sha256_str(stable_json_dumps(context))
