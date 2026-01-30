# core/generation/sentence_ledger.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


class SentenceLedger:
    def __init__(self, store: Any, key: str):
        self.store = store
        self.key = key  # p.ej. "audit/language_sentences/v1/events.jsonl"

    def append(self, record: Dict[str, Any]) -> None:
        rec = dict(record)
        rec["ts"] = datetime.now(timezone.utc).isoformat()
        self.store.append_jsonl(self.key, rec)
