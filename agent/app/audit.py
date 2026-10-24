"""Append-only hash-chained audit log: hash = sha256(prev_hash + canonical_json(event))."""
import hashlib
import json
from .db import get_conn, lock
from .models import now_iso

GENESIS = "0" * 64


def canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev: str, event_json: str) -> str:
    return hashlib.sha256((prev + event_json).encode()).hexdigest()


def append(event_type: str, payload: dict) -> dict:
    with lock():
        c = get_conn()
        row = c.execute("SELECT hash FROM audit ORDER BY idx DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        ev = canonical({"type": event_type, **payload})
        h = _hash(prev, ev)
        ts = now_iso()
        cur = c.execute("INSERT INTO audit (ts, event, prev_hash, hash) VALUES (?,?,?,?)", (ts, ev, prev, h))
        c.commit()
        return {"idx": cur.lastrowid, "ts": ts, "event": json.loads(ev), "prev_hash": prev, "hash": h}


def entries(limit: int = 500) -> list[dict]:
    rows = get_conn().execute("SELECT * FROM audit ORDER BY idx ASC LIMIT ?", (limit,)).fetchall()
    return [{"idx": r["idx"], "ts": r["ts"], "event": json.loads(r["event"]),
             "prev_hash": r["prev_hash"], "hash": r["hash"]} for r in rows]


def verify() -> dict:
    prev = GENESIS
    rows = get_conn().execute("SELECT * FROM audit ORDER BY idx ASC").fetchall()
    for r in rows:
        if r["prev_hash"] != prev or _hash(prev, r["event"]) != r["hash"]:
            return {"ok": False, "first_broken_idx": r["idx"], "length": len(rows)}
        prev = r["hash"]
    return {"ok": True, "first_broken_idx": None, "length": len(rows)}
