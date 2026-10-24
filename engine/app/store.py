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
from .models import Evidence, Reason, Score, Ticket, TicketWithScore
from .scoring import baseline_score, from_row
from .scorer import runtime

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = Path(os.environ.get("CONTRACT_DIR", ROOT / "contract"))
WAREHOUSE_DIR = Path(os.environ.get("WAREHOUSE_DIR", ROOT / "data" / "warehouse"))

TICKET_COLUMNS = ["ticket_id", "city", "data_quality", "source", "category", "text", "lang", "lat", "lng", "h3",
                  "location_precision", "ward", "created_at", "closed_at", "closed_by_hash", "status",
                  "closure_note", "closure_photo_url", "complaint_photo_url"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(name: str):
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


VERIFIER_METRICS = ("satellite", "benchmark_v1")


def _all_metrics() -> dict:
    """Real evaluation metrics written by the training and validation scripts, keyed by file name."""
    out = {}
    for f in sorted(runtime.MODELS.glob("*.metrics.json")) if runtime.MODELS.exists() else []:
        out[f.name.removesuffix(".metrics.json")] = json.loads(f.read_text(encoding="utf-8"))
    return out


def _eval_payload() -> dict:
    base, found = _load("eval_results.json"), _all_metrics()
    scorers = {k: v for k, v in found.items() if k not in VERIFIER_METRICS}
    verifiers = {k: found[k] for k in VERIFIER_METRICS if k in found}
    return {"is_placeholder": not scorers and not verifiers,
            "scorers": scorers,
            "verifiers": verifiers if verifiers else base.get("verifiers", []),
            "verifiers_are_placeholder": len(verifiers) < len(VERIFIER_METRICS),
            "pending": ["agent cost versus accuracy (needs the Agent service's real verifiers)",
                        "photo content checks (need the demo photo set)"],
            "note": "scorers and verifiers hold real metrics with their own caveats; benchmark numbers are synthetic injection."}


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
        self._load_overrides()
        self._build()
        self.eval_results = _eval_payload()

    def _build(self) -> None:
        files = sorted(str(f) for f in self._dir.glob("tickets_*.parquet"))
        if not files:
            raise FileNotFoundError(f"no tickets_*.parquet in {self._dir}; run `python -m app.ingest all`")
        self._con.execute("drop view if exists v")
        self._con.execute("drop table if exists tickets")
        self._con.execute("create table tickets as select * from read_parquet(?, union_by_name=true)", [files])
        # only the demo set carries a "before" photo: keep the column when that file is absent
        self._con.execute("alter table tickets add column if not exists complaint_photo_url varchar")
        self._con.execute("create view v as select t.* replace (coalesce(o.status, t.status) as status) "
                          "from tickets t left join status_overrides o on o.ticket_id = t.ticket_id")
        self._con.execute("drop view if exists vs")
        self._con.execute("drop table if exists scores")
        score_files = sorted(str(f) for f in self._dir.glob("scores_*.parquet"))
        if score_files:
            self._con.execute("create table scores as select ticket_id, p_false_closure, score_type, risk_percentile, "
                              "model_version, flags from read_parquet(?, union_by_name=true)", [score_files])
        else:
            self._con.execute("create table scores (ticket_id varchar, p_false_closure double, score_type varchar, "
                              "risk_percentile double, model_version varchar, flags varchar)")
        # tickets of a not-yet-scored kind get NULL score columns and fall back to the neutral baseline
        self._con.execute("create view vs as select v.*, s.p_false_closure as _p, s.score_type as _score_type, "
                          "s.risk_percentile as _pct, s.model_version as _mv, s.flags as _flags "
                          "from v left join scores s on s.ticket_id = v.ticket_id")

    def _rows(self, sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._con.cursor()
            cur.execute(sql, params or [])
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    # ---- tickets ----
    _SCORE_COLS = "_p, _score_type, _pct, _mv, _flags"

    def list_tickets(self, *, city=None, ward=None, category=None, status=None, min_score=0.0, limit=100, offset=0,
                     sort="newest") -> list[TicketWithScore]:
        where, params = [], []
        for col, val in (("city", city), ("ward", ward), ("category", category), ("status", status)):
            if val:
                where.append(f"{col} = ?")
                params.append(val)
        if min_score > 0:
            where.append("coalesce(_p, 0.5) >= ?")
            params.append(min_score)
        sql = f"select {', '.join(TICKET_COLUMNS)}, {self._SCORE_COLS} from vs"
        if where:
            sql += " where " + " and ".join(where)
        order = "coalesce(_p, 0.5) desc, created_at desc" if sort == "risk" else "created_at desc"
        sql += f" order by {order}, ticket_id limit ? offset ?"
        out = []
        for row in self._rows(sql, params + [limit, offset]):
            t = Ticket(**{k: row[k] for k in TICKET_COLUMNS})
            out.append(TicketWithScore(ticket=t, score=from_row(t, row)))  # reasons are only computed by /score
        return out

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        rows = self._rows(f"select {', '.join(TICKET_COLUMNS)} from v where ticket_id = ?", [ticket_id])
        return Ticket(**rows[0]) if rows else None

    def get_score(self, ticket_id: str) -> Optional[Score]:
        rows = self._rows(f"select {', '.join(TICKET_COLUMNS)}, {self._SCORE_COLS} from vs where ticket_id = ?", [ticket_id])
        if not rows:
            return None
        t = Ticket(**{k: rows[0][k] for k in TICKET_COLUMNS})
        score = from_row(t, rows[0])
        score.reasons = [Reason(**r) for r in runtime.reasons(t.ticket_id, t.city, rows[0]["_mv"], rows[0]["_flags"] or "", self._dir)]
        return score

    def satellite_evidence(self, ticket_id: str, cached_only: bool = False, refresh: bool = False) -> Evidence:
        from .satellite import verifier  # lazy: pulls in rasterio and pystac-client
        t = self.get_ticket(ticket_id)
        return Evidence(**verifier.check_ticket(t.model_dump(), cached_only=cached_only, refresh=refresh))

    def _overrides_path(self) -> Path:
        return self._dir / "status_overrides.json"

    def _load_overrides(self) -> None:
        """The simulated municipal system must remember reopens across an Engine restart."""
        try:
            saved = json.loads(self._overrides_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for tid, status in saved.items():
            self._con.execute("insert or replace into status_overrides values (?, ?)", [tid, status])

    def set_status(self, ticket_id: str, status: str) -> None:
        with self._lock:
            cur = self._con.cursor()
            cur.execute("delete from status_overrides where ticket_id = ?", [ticket_id])
            cur.execute("insert into status_overrides values (?, ?)", [ticket_id, status])
            saved = dict(cur.execute("select ticket_id, status from status_overrides").fetchall())
        tmp = self._overrides_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(saved), encoding="utf-8")
        tmp.replace(self._overrides_path())

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

    def list_tickets(self, *, city=None, ward=None, category=None, status=None, min_score=0.0, limit=100, offset=0,
                     sort="newest") -> list[TicketWithScore]:
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

    def satellite_evidence(self, ticket_id: str, cached_only: bool = False, refresh: bool = False) -> Evidence:
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
