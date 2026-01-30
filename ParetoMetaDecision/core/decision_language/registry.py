from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from core.artifacts.store import ArtifactStore
from dataclasses import dataclass
from core.artifacts.store import ArtifactStore, ArtifactKey

LanguageState = str  # "draft" | "candidate" | "approved" | "deprecated" | "banned"


def _utc_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass(frozen=True)
class LanguageId:
    language_key: str
    version: str = "v1"


class LanguageRegistry:
    """
    Domain-agnostic registry for decision language artifacts (AST).
    Backed by ArtifactStore for stable persistence + future MapA9 governance.
    """

    def __init__(self, store: ArtifactStore, namespace: str = "language_registry"):
        self.store = store
        self.namespace = namespace

    @dataclass(frozen=True)
    class StoreKey:
        problem: str
        name: str
        version: str
        context_key: str

    def _key(self, lid: LanguageId) -> ArtifactKey:
        return ArtifactKey(
            problem="core",                 # domain-agnostic
            dataset_id="_global_",          # lenguaje no depende de dataset
            name=f"{self.namespace}/ast",   # tipo de artefacto
            params={"language_key": lid.language_key},
            version=lid.version,
        )

    def get(self, lid: LanguageId) -> Optional[Dict[str, Any]]:
        return self.store.get(self._key(lid))

    def upsert_ast(self, lid: LanguageId, ast_dict: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.get(lid)
        now = _utc_ts()

        if rec is None:
            rec = {
                "language_key": lid.language_key,
                "version": lid.version,
                "state": "draft",
                "ast": ast_dict,
                "created_at": now,
                "updated_at": now,
                "notes": "",
                "history": [
                    {"ts": now, "event": "create", "notes": ""},
                ],
            }
        else:
            rec["ast"] = ast_dict
            rec["updated_at"] = now
            rec.setdefault("history", []).append({"ts": now, "event": "update_ast", "notes": ""})

        self.store.put(self._key(lid), rec)
        return rec

    def get_state(self, lid: LanguageId) -> LanguageState:
        rec = self.get(lid)
        return (rec.get("state") if rec else None) or "draft"

    def set_state(self, lid: LanguageId, state: LanguageState, notes: str = "") -> Dict[str, Any]:
        rec = self.get(lid)
        now = _utc_ts()

        if rec is None:
            # allow setting state even if AST not registered yet
            rec = {
                "language_key": lid.language_key,
                "version": lid.version,
                "state": state,
                "ast": {},
                "created_at": now,
                "updated_at": now,
                "notes": notes,
                "history": [{"ts": now, "event": f"set_state:{state}", "notes": notes}],
            }
        else:
            rec["state"] = state
            rec["updated_at"] = now
            if notes:
                rec["notes"] = notes
            rec.setdefault("history", []).append({"ts": now, "event": f"set_state:{state}", "notes": notes})

        self.store.set(self._key(lid), rec)
        return rec
