"""Fill the satellite cache for demo tickets so the demo works if the imagery archive or the network is slow.

Real: Mumbai tickets whose wording names a large-area problem (dump sites, nullah corridors, large unauthorised structures),
closed between mid-April and the end of August 2026, exact location. Small problems are "not applicable" and never cached.
Synthetic: a few Pune and Sandbox tickets, which the verifier marks demo_only (real imagery, invented ticket, no weight).
Every ticket is cached whether it measured or abstained: abstentions are part of the honest picture (monsoon clouds).

Usage (from engine/):  python -m app.satellite.precompute --n 30
"""
import argparse
import json
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from ..eligibility import is_large_area
from . import verifier

ROOT = Path(__file__).resolve().parents[3]
COLS = "ticket_id, category, text, lat, lng, created_at, closed_at, location_precision, data_quality"


def pick(n: int, seed: int = 7) -> list[dict]:
    con, rng = duckdb.connect(), random.Random(seed)
    out = []
    keys = COLS.replace(" ", "").split(",")
    for cat in ("garbage", "drain", "other"):
        rows = con.execute(f"select {COLS} from read_parquet(?) where status='closed' and location_precision='exact' and category=? "
                           "and closed_at between '2026-04-15' and '2026-08-31' and created_at >= '2026-04-01'",
                           [str(ROOT / "data/warehouse/tickets_mumbai.parquet"), cat]).fetchall()
        rows = [r for r in rows if is_large_area(r[2])]
        rng.shuffle(rows)
        out += [dict(zip(keys, r)) for r in rows[:n]]
    for city, file in (("pune", "tickets_pune.parquet"), ("synthetic", "tickets_synthetic.parquet")):
        rows = con.execute(f"select {COLS} from read_parquet(?) where status='closed' and category in ('garbage','drain','other') "
                           "and closed_at is not null", [str(ROOT / "data/warehouse" / file)]).fetchall()
        rows = [r for r in rows if is_large_area(r[2])]   # synthetic wording carries no scale, so this is usually empty
        rng.shuffle(rows)
        out += [dict(zip(keys, r)) for r in rows[:4]]
    return out


def run(n: int = 30, workers: int = 3, refresh: bool = False) -> dict:
    tickets = pick(n)
    t0 = time.time()

    def one(t):
        t1 = time.time()
        ev = verifier.check_ticket(t, refresh=refresh)
        return {"ticket_id": t["ticket_id"], "city": t["ticket_id"].split("-")[0], "category": t["category"], "verdict": ev["verdict"],
                "reason": ev["details"].get("reason"), "demo_only": ev["details"].get("demo_only", False),
                "percentile": ev["details"].get("percentile"), "seconds": round(time.time() - t1, 1), "source": ev["details"].get("source")}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(one, tickets))
    measured = [r for r in res if r["percentile"] is not None]
    summary = {"tickets": len(res), "measured": len(measured), "abstained_or_ineligible": len(res) - len(measured),
               "verdicts": dict(Counter(r["verdict"] for r in res)), "reasons": dict(Counter(r["reason"] for r in res if r["reason"])),
               "seconds_total": round(time.time() - t0, 1), "results": res}
    (ROOT / "data" / "cache").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "cache" / "satellite_precompute.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    s = run(a.n, a.workers, a.refresh)
    print({k: v for k, v in s.items() if k != "results"})
