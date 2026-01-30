# core/utils/imports.py
from __future__ import annotations
import importlib
from typing import Any, Callable

def import_from_string(ref: str) -> Callable[..., Any]:
    module_name, attr = ref.split(":", 1)
    mod = importlib.import_module(module_name)
    fn = getattr(mod, attr)
    if not callable(fn):
        raise TypeError(f"Ref is not callable: {ref}")
    return fn
