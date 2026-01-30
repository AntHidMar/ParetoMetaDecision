# core/optimization_tracker.py
import json
from datetime import datetime
from typing import Any, Dict, Optional


class OptimizationTracker:
    def __init__(self):
        self.records = []

    def log(
        self,
        params: Dict[str, Any],
        metrics: Dict[str, Any],
        utility: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Logs any parameter dictionary, including nested/composed rules (AND/OR)
        and arbitrary variables. No assumptions about keys like theta/k/horizon.
        """
        record = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "params": params,         # keep full dict (can be nested)
            "metrics": metrics,       # keep full metrics dict
            "utility": utility,
            "meta": meta or {},
            # Optional: stable string for grouping/comparison/debugging
            "params_json": json.dumps(params, sort_keys=True, ensure_ascii=False),
        }
        self.records.append(record)
