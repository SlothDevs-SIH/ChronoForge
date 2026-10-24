"""Satellite verifier: turns one closed ticket into Evidence.

  eligible?  (large-area wording, exact point, has a closing date)  ->  else inconclusive at cost 0
  cached?    data/cache/satellite/<ticket_id>.json         ->  else live read from Sentinel-2
  live: choose a same-tile before/after pair, read a ~3 km window of each, compare the site with matched controls

What the result means, honestly: it says whether the site changed unusually between the two dates compared with similar
nearby places. Small works are invisible at 10 m, so "no unusual change" is weak evidence and the likelihood ratios are
deliberately small. The ratios rest on stated assumptions and were NOT validated against real repair outcomes (there are
none); validation covers the null (placebo) and sensitivity (injected change). See data/models/satellite.metrics.json.
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..eligibility import satellite_eligibility
from . import change, reader, scenes

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("SAT_CACHE_DIR", ROOT / "data" / "cache" / "satellite"))

CONTEXT_HALF_M = 1600           # context window: about 3.2 km square around the site
SITE_HALF_PX = 6                # site window: 13 x 13 pixels, about 130 m
DETECT_PCT = 0.90               # "unusual change": site change magnitude above 90% of the matched controls
# Likelihood ratios P(evidence | not fixed) / P(evidence | fixed). ASSUMPTIONS, see assumptions() and the metrics file.
LR_DETECT = 0.45                # unusual change seen: leans "fixed"
LR_NO_DETECT = 1.25             # no unusual change: only weakly leans "not fixed" (small works are invisible at 10 m)


def assumptions() -> dict:
    return {"P_detect_given_fixed": 0.40, "P_detect_given_not_fixed": 0.18,
            "LR_detect": round(0.18 / 0.40, 2), "LR_no_detect": round((1 - 0.18) / (1 - 0.40), 2),
            "meaning": "Assumed, not measured on real repairs. 40% is what the validation measured for an injected change of about 1.5 control "
                       "spreads (roughly 0.04 NDVI and 0.03 NDBI), i.e. we assume a real repair changes the site by about that much; 18% is "
                       "slightly above the 13% unusual-change rate seen at random places with no repair claimed (95% CI 3% to 34%). "
                       "The arithmetic gives ratios 0.45 and 1.37; we ship 0.45 and a more cautious 1.25 because small works are invisible at 10 m."}


def _evidence(ticket_id: str, verdict: str, lr: float, conf: float, cost: int, details: dict) -> dict[str, Any]:
    return {"evidence_id": str(uuid.uuid4()), "ticket_id": ticket_id, "check": "satellite", "verdict": verdict,
            "likelihood_ratio": lr, "confidence": conf, "cost": cost, "details": details,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _chip(refl: np.ndarray, half_px: int = 20, scale: int = 4, box_half: int = SITE_HALF_PX) -> "Image":
    from PIL import Image, ImageDraw
    h, w = refl.shape[1:]
    cy, cx = h // 2, w // 2
    crop = refl[[2, 1, 0], cy - half_px:cy + half_px + 1, cx - half_px:cx + half_px + 1]
    rgb = (np.clip(crop.transpose(1, 2, 0) * 3.5, 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(rgb).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.NEAREST)
    c, r = half_px * scale + scale // 2, box_half * scale
    ImageDraw.Draw(img).rectangle([c - r, c - r, c + r, c + r], outline=(255, 200, 0), width=2)
    return img


def cache_path(ticket_id: str) -> Path:
    return CACHE_DIR / f"{ticket_id}.json"


def chip_path(ticket_id: str, which: str) -> Path:
    return CACHE_DIR / f"{ticket_id}_{which}.png"


def _read_with_retry(scene, bbox, tries: int = 2):
    """One more attempt at the whole window if the band-level retries were not enough (a failed read is our network, not the data)."""
    for i in range(tries):
        try:
            return reader.read_window(scene.hrefs, scene.baseline, bbox)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3)


def _transient(reason: str) -> bool:
    """Failures that say nothing about the ticket and must never be cached."""
    return reason.startswith("imagery read failed")


def measure(lat: float, lng: float, created: datetime, closed: datetime, client=None) -> dict:
    """Live measurement. Returns analysis dict (with 'abstain' on failure) plus 'before'/'after' scene info and windows."""
    t0 = time.time()
    before, after, note = scenes.choose_pair(lat, lng, created, closed, client)
    if before is None:
        return {"abstain": note, "seconds": round(time.time() - t0, 1)}
    bbox = reader.context_bbox(lat, lng, CONTEXT_HALF_M)
    wb = _read_with_retry(before, bbox)
    wa = _read_with_retry(after, bbox)
    if wb.refl.shape != wa.refl.shape or wb.transform != wa.transform:
        return {"abstain": "before and after windows are not on the same pixel grid", "seconds": round(time.time() - t0, 1)}
    res = change.analyse(wb.refl, wa.refl, wb.scl, wa.scl, site_half=SITE_HALF_PX)
    res.update(before=before.brief(), after=after.brief(), seconds=round(time.time() - t0, 1),
               days_before_filing=(created - before.when).days, days_after_closing=(after.when - closed).days,
               _win_before=wb, _win_after=wa)
    return res


def _from_analysis(res: dict) -> tuple[str, float, float, dict]:
    """(verdict, lr, confidence, details) from an analysis dict."""
    if "abstain" in res:
        return "inconclusive", 1.0, 0.0, {"eligible": True, "abstained": True, "reason": res["abstain"]}
    details = {"eligible": True, "abstained": False, "before_scene": res["before"], "after_scene": res["after"],
               "days_before_filing": res["days_before_filing"], "days_after_closing": res["days_after_closing"],
               "site_valid_fraction": res["site_valid"], "n_controls": res["n_controls"],
               "control_match_distance": res["match_distance_median"], "percentile": res["percentile"],
               "z_score": res["z_score"], "feature_z": res["feature_z"], "site_delta": res["site_delta"],
               "control_sigma": res["control_sigma"], "detect_threshold_percentile": DETECT_PCT,
               "lr_basis": assumptions()["meaning"]}
    if res["percentile"] >= DETECT_PCT:
        return "supports_fix", LR_DETECT, 0.35, {**details, "reading": "the site changed unusually compared with similar nearby places"}
    return "contradicts_fix", LR_NO_DETECT, 0.2, {**details, "reading": "no unusual change at the site; small works would not show at 10 m, so this is weak evidence"}


def check_ticket(t: dict, cached_only: bool = False, refresh: bool = False, client=None) -> dict[str, Any]:
    """t: ticket fields (ticket_id, category, text, lat, lng, created_at, closed_at, location_precision, data_quality)."""
    tid = t["ticket_id"]
    ok, reason = satellite_eligibility(t["category"], t.get("location_precision"), t.get("text"))
    if ok and not t.get("closed_at"):
        ok, reason = False, "no closing date, so there is no 'after' to compare"
    if not ok:
        return _evidence(tid, "inconclusive", 1.0, 0.0, 0, {"eligible": False, "reason": reason})
    demo = t.get("data_quality") == "synthetic"

    path = cache_path(tid)
    if path.exists() and not refresh:
        c = json.loads(path.read_text(encoding="utf-8"))
        c["details"]["source"] = "cached"
        return _evidence(tid, c["verdict"], c["likelihood_ratio"], c["confidence"], 3, c["details"])
    if cached_only:
        return _evidence(tid, "inconclusive", 1.0, 0.0, 0, {"eligible": True, "abstained": True, "source": "not_cached",
                                                            "reason": "no cached measurement for this ticket and live reads were not requested"})
    try:
        res = measure(t["lat"], t["lng"], _parse(t["created_at"]), _parse(t["closed_at"]), client)
    except Exception as exc:  # network, GDAL and archive errors must abstain, never crash the agent
        res = {"abstain": f"imagery read failed: {type(exc).__name__}: {str(exc)[:120]}"}
    verdict, lr, conf, details = _from_analysis(res)
    details["source"] = "live"
    if "seconds" in res:
        details["seconds"] = res["seconds"]
    if demo and verdict != "inconclusive":
        # the imagery is real but the ticket is synthetic: the measurement says nothing about a fix, so it carries no weight
        details.update(demo_only=True, reading_note="synthetic ticket: real imagery at generated coordinates, so this cannot reflect a repair",
                       measured_verdict=verdict, measured_lr=lr)
        verdict, lr, conf = "inconclusive", 1.0, 0.0
    if "_win_before" in res:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _chip(res["_win_before"].refl).save(chip_path(tid, "before"))
        _chip(res["_win_after"].refl).save(chip_path(tid, "after"))
        details["chip_before_url"], details["chip_after_url"] = f"/satellite/chip/{tid}/before.png", f"/satellite/chip/{tid}/after.png"
    if verdict == "inconclusive" and _transient(details.get("reason", "")):
        return _evidence(tid, verdict, lr, conf, 3, details)   # a network failure is not a finding: do not cache it
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"verdict": verdict, "likelihood_ratio": lr, "confidence": conf, "details": details}, indent=1), encoding="utf-8")
    return _evidence(tid, verdict, lr, conf, 3, details)
