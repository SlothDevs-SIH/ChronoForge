"""Data access for the API. Two backends behind one interface:

  WarehouseStore  the real tickets: DuckDB over the Parquet files written by `python -m app.ingest`
  FixtureStore    the six contract fixtures (tests, or a Docker image with no data)

ENGINE_DATA_MODE = auto (default: warehouse if Parquet files exist, else fixtures) | warehouse | fixtures
WAREHOUSE_DIR    overrides data/warehouse
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb

from .eligibility import satellite_eligibility
from .models import Evidence, Score, Ticket, TicketWithScore
from .scoring import baseline_score

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = Path(os.environ.get("CONTRACT_DIR", ROOT / "contract"))
WAREHOUSE_DIR = Path(os.environ.get("WAREHOUSE_DIR", ROOT / "data" / "warehouse"))

TICKET_COLUMNS = ["ticket_id", "city", "data_quality", "source", "category", "text", "lang", "lat", "lng", "h3",
                  "location_precision", "ward", "created_at", "closed_at", "closed_by_hash", "status",
                  "closure_note", "closure_photo_url"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(name: str):
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def _inconclusive(ticket_id: str, cost: int, details: dict[str, Any]) -> Evidence:
    return Evidence(evidence_id=str(uuid.uuid4()), ticket_id=ticket_id, check="satellite", verdict="inconclusive",
                    likelihood_ratio=1.0, confidence=0.0, cost=cost, details=details, created_at=_now())


class WarehouseStore:
    """All queries run against the view `v`: tickets with status changes from the simulated municipal system
    applied (table `status_overrides`), so lists, filters and stats always agree."""
    mode = "warehouse"

    def __init__(self, directory: Path = WAREHOUSE_DIR) -> None:
        self._dir = directory
        self._lock = threading.Lock()
        self._con = duckdb.connect()
        self._con.execute("create table status_overrides (ticket_id varchar primary key, status varchar)")
        self._build()
        self.eval_results: dict = _load("eval_results.json")

    def _build(self) -> None:
        files = sorted(str(f) for f in self._dir.glob("tickets_*.parquet"))
        if not files:
            raise FileNotFoundError(f"no tickets_*.parquet in {self._dir}; run `python -m app.ingest all`")
        self._con.execute("drop view if exists v")
        self._con.execute("drop table if exists tickets")
        self._con.execute("create table tickets as select * from read_parquet(?, union_by_name=true)", [files])
        self._con.execute("create view v as select t.* replace (coalesce(o.status, t.status) as status) "
                          "from tickets t left join status_overrides o on o.ticket_id = t.ticket_id")

    def _rows(self, sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._con.cursor()
            cur.execute(sql, params or [])
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    # ---- tickets ----
    def list_tickets(self, *, city=None, ward=None, category=None, status=None, min_score=0.0, limit=100, offset=0
                     ) -> list[TicketWithScore]:
        if min_score > baseline_score("x", "other", None).p_false_closure:
            return []  # the baseline prior is the only score until the Phase 3 scorer exists
        where, params = [], []
        for col, val in (("city", city), ("ward", ward), ("category", category), ("status", status)):
            if val:
                where.append(f"{col} = ?")
                params.append(val)
        sql = f"select {', '.join(TICKET_COLUMNS)} from v"
        if where:
            sql += " where " + " and ".join(where)
        sql += " order by created_at desc, ticket_id limit ? offset ?"
        out = []
        for row in self._rows(sql, params + [limit, offset]):
            t = Ticket(**row)
            out.append(TicketWithScore(ticket=t, score=baseline_score(t.ticket_id, t.category, t.location_precision)))
        return out

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        rows = self._rows(f"select {', '.join(TICKET_COLUMNS)} from v where ticket_id = ?", [ticket_id])
        return Ticket(**rows[0]) if rows else None

    def get_score(self, ticket_id: str) -> Optional[Score]:
        t = self.get_ticket(ticket_id)
        return baseline_score(t.ticket_id, t.category, t.location_precision) if t else None

    def satellite_evidence(self, ticket_id: str) -> Evidence:
        t = self.get_ticket(ticket_id)
        ok, reason = satellite_eligibility(t.category, t.location_precision)
        if not ok:
            return _inconclusive(ticket_id, 0, {"eligible": False, "reason": reason})
        # Eligible, but the verifier is Phase 4. Say so instead of inventing a result.
        return _inconclusive(ticket_id, 3, {"eligible": True, "stub": True,
                                            "reason": "satellite verifier not built yet; no change measured"})

    def set_status(self, ticket_id: str, status: str) -> None:
        with self._lock:
            cur = self._con.cursor()
            cur.execute("delete from status_overrides where ticket_id = ?", [ticket_id])
            cur.execute("insert into status_overrides values (?, ?)", [ticket_id, status])

    def muni_tickets(self, limit: int) -> list[Ticket]:
        return [x.ticket for x in self.list_tickets(limit=limit)]

    # ---- aggregates ----
    def ward_stats(self, city: Optional[str], category: Optional[str]) -> list[dict[str, Any]]:
        where, params = [], []
        for col, val in (("city", city), ("category", category)):
            if val:
                where.append(f"{col} = ?")
                params.append(val)
        sql = ("select city, ward, category, count(*) as tickets, "
               "sum((status='closed')::int)::int as closed, sum((status='reopened')::int)::int as reopened, "
               "sum((status='open')::int)::int as open from v"
               + (" where " + " and ".join(where) if where else "")
               + " group by city, ward, category order by tickets desc")
        out = []
        for r in self._rows(sql, params):
            done = r["closed"] + r["reopened"]
            out.append({
                "city": r["city"], "ward": r["ward"], "category": r["category"], "tickets": r["tickets"],
                "closed": r["closed"], "reopened": r["reopened"], "open": r["open"],
                "official_rate": round(done / r["tickets"], 4),
                "reopen_rate": round(r["reopened"] / done, 4) if done else None,
                "honest_rate": None,  # needs the Phase 3 scorer
            })
        return out

    def cities(self) -> list[dict[str, Any]]:
        return self._rows(
            "select city, count(*)::int as tickets, sum((status='closed')::int)::int as closed, "
            "sum((status='reopened')::int)::int as reopened, sum((status='open')::int)::int as open, "
            "any_value(data_quality) as data_quality, any_value(location_precision) as location_precision "
            "from v group by city order by tickets desc")

    def reload(self) -> None:
        with self._lock:
            self._build()


class FixtureStore:
    mode = "fixtures"

    def __init__(self) -> None:
        self.tickets: dict[str, Ticket] = {t["ticket_id"]: Ticket(**t) for t in _load("tickets.json")}
        self.scores: dict[str, Score] = {k: Score(**v) for k, v in _load("scores.json").items()}
        self._ward_stats: list[dict] = _load("ward_stats.json")
        self.eval_results: dict = _load("eval_results.json")
        self._evidence: dict = _load("evidence.json")

    def list_tickets(self, *, city=None, ward=None, category=None, status=None, min_score=0.0, limit=100, offset=0
                     ) -> list[TicketWithScore]:
        out = []
        for t in self.tickets.values():
            s = self.scores[t.ticket_id]
            if (city and t.city != city) or (ward and t.ward != ward) or (category and t.category != category) \
                    or (status and t.status != status) or s.p_false_closure < min_score:
                continue
            out.append(TicketWithScore(ticket=t, score=s))
        out.sort(key=lambda x: x.score.p_false_closure, reverse=True)
        return out[offset:offset + limit]

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        return self.tickets.get(ticket_id)

    def get_score(self, ticket_id: str) -> Optional[Score]:
        return self.scores.get(ticket_id)

    def satellite_evidence(self, ticket_id: str) -> Evidence:
        key = "satellite" if self.scores[ticket_id].satellite_eligible else "satellite_ineligible"
        ev = dict(self._evidence[key])
        ev.update(ticket_id=ticket_id, evidence_id=str(uuid.uuid4()), created_at=_now())
        return Evidence(**ev)

    def set_status(self, ticket_id: str, status: str) -> None:
        self.tickets[ticket_id].status = status

    def muni_tickets(self, limit: int) -> list[Ticket]:
        return list(self.tickets.values())[:limit]

    def ward_stats(self, city: Optional[str], category: Optional[str]) -> list[dict[str, Any]]:
        return [w for w in self._ward_stats if (not city or w["city"] == city) and (not category or w["category"] == category)]

    def cities(self) -> list[dict[str, Any]]:
        by: dict[str, dict] = {}
        for t in self.tickets.values():
            c = by.setdefault(t.city, {"city": t.city, "tickets": 0, "closed": 0, "reopened": 0, "open": 0,
                                       "data_quality": t.data_quality, "location_precision": t.location_precision})
            c["tickets"] += 1
            c[t.status] += 1
        return list(by.values())

    def reload(self) -> None:
        pass


def load_store():
    mode = os.environ.get("ENGINE_DATA_MODE", "auto")
    if mode == "fixtures":
        return FixtureStore()
    if mode == "warehouse":
        return WarehouseStore()
    return WarehouseStore() if list(WAREHOUSE_DIR.glob("tickets_*.parquet")) else FixtureStore()


store = load_store()
