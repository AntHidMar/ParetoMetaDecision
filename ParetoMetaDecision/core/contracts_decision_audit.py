# core/contracts_decision_audit.py
from __future__ import annotations

from typing import Final

# Reason codes (controlados). No uses strings libres en producción.
ALLOWED_FIRE: Final[str] = "ALLOWED_FIRE"
ALLOWED_NOFIRE: Final[str] = "ALLOWED_NOFIRE"
BLOCKED_BY_SCHEDULE: Final[str] = "BLOCKED_BY_SCHEDULE"
FORCED_ABSTAIN_GUARDRAIL: Final[str] = "FORCED_ABSTAIN_GUARDRAIL"
SAFE_MODE: Final[str] = "SAFE_MODE"
