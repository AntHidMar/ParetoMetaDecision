# core/utils/yaml_io.py (o dentro del plugin si prefieres)
from __future__ import annotations
from typing import Any, Dict
import yaml

def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
