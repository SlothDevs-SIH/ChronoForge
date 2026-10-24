"""Append-only, hash-chained audit log. hash = sha256(prev_hash + canonical_json(event))."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

GENESIS = "0" * 64


def _digest(prev_hash: str, event: dict[str, Any]) -> str:
    payload = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        prev = self.rows[-1]["hash"] if self.rows else GENESIS
        event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        row = {"idx": len(self.rows), "event": event, "prev_hash": prev, "hash": _digest(prev, event)}
        self.rows.append(row)
        return row

    def verify(self) -> dict[str, Any]:
        prev = GENESIS
        for row in self.rows:
            if row["prev_hash"] != prev or row["hash"] != _digest(prev, row["event"]):
                return {"ok": False, "first_bad_index": row["idx"], "length": len(self.rows)}
            prev = row["hash"]
        return {"ok": True, "first_bad_index": None, "length": len(self.rows)}
