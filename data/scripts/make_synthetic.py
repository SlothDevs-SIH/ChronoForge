"""Generate synthetic complaint cities with known ground truth.

Two outputs (data/processed/):
  synthetic_pune.csv   city=pune       synthetic complaints placed on REAL Pune wards and REAL drain (nalla) lines
  synthetic_city.csv   city=synthetic  fully fictional city ("Sandbox City"), a 6x5 ward grid over land near Nashik

WHAT IS REAL: Pune ward polygons and drain lines (PMC open data via OpenCity); resolution-time shape
(from BMC MARG, Mumbai).  WHAT IS INVENTED: every complaint, every closure, every false-closure label,
the false-closure rates, the failure modes, the officer behaviour and the category mix (borrowed from the
BBMP and Mumbai mixes, not Pune's).  Say so wherever these numbers are shown.

Columns starting gt_ are ground truth for the benchmark. They MUST NOT be used as scorer features
or shown in the UI.  Photos: closure_photo_id points at a demo-photo slot; the photo set is built separately.

Run from repo root:  python data/scripts/make_synthetic.py [--n 5000] [--seed 7]
"""
import argparse
import csv
import hashlib
import math
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h3
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
NS = {"k": "http://www.opengis.net/kml/2.2"}
WINDOW_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc)

# category: (weight, median_h, p90_h, base false-closure rate)
# resolution times: pothole from BMC MARG pothole layer (median 44.8 h, p90 133 h);
# others from BMC MARG complaints overall (median 207 h, p90 1793 h). Base false rates are ASSUMPTIONS.
CATS = {
    "streetlight": (0.30, 207, 1793, 0.10),
    "garbage": (0.28, 207, 1793, 0.18),
    "pothole": (0.15, 44.8, 133, 0.22),
    "drain": (0.10, 207, 1793, 0.20),
    "water_leak": (0.07, 207, 1793, 0.12),
    "other": (0.10, 207, 1793, 0.12),
}
SATELLITE_CATS = {"garbage", "drain"}  # large enough sites to sometimes show from orbit
MAX_RES_H = 90 * 24

TEXT = {
    "pothole": {"en": "Large pothole on the road, vehicles are slowing down.", "mr": "रस्त्यावर मोठा खड्डा पडला आहे.", "hi": "सड़क पर बड़ा गड्ढा है।"},
    "garbage": {"en": "Garbage has not been cleared for several days.", "mr": "कचरा अनेक दिवस उचललेला नाही.", "hi": "कई दिनों से कचरा नहीं उठाया गया।"},
    "streetlight": {"en": "Streetlight is not working on this road.", "mr": "रस्त्यावरील दिवा बंद आहे.", "hi": "सड़क की बत्ती बंद है।"},
    "drain": {"en": "Drain is blocked and water is overflowing onto the road.", "mr": "गटार तुंबले आहे, पाणी रस्त्यावर येत आहे.", "hi": "नाला जाम है, पानी सड़क पर आ रहा है।"},
    "water_leak": {"en": "Water pipeline is leaking.", "mr": "पाण्याची पाईपलाईन फुटली आहे.", "hi": "पानी की पाइपलाइन फूटी है।"},
    "other": {"en": "There is a civic problem in this area, please inspect.", "mr": "परिसरात समस्या आहे, कृपया पाहणी करा.", "hi": "इलाके में समस्या है, कृपया जाँच करें।"},
}
GOOD_NOTES = ["Work completed and verified with the complainant.", "Repaired; site cleaned after the work.", "Attended, fault fixed, photo uploaded.", "Done."]
FIELDS = ["ticket_id", "city", "data_quality", "source", "category", "text", "lang", "lat", "lng", "h3", "ward",
          "created_at", "closed_at", "closed_by_hash", "status", "closure_note", "closure_photo_id",
          "closure_photo_exif_dist_m", "gt_false_closure", "gt_failure_mode", "gt_site_changed"]


def lognormal(rng, median, p90):
    return rng.lognormvariate(math.log(median), (math.log(p90) - math.log(median)) / 1.2816)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jitter(rng, lat, lng, metres):
    r = abs(rng.gauss(0, metres))
    a = rng.uniform(0, 2 * math.pi)
    return lat + r * math.cos(a) / 111_320, lng + r * math.sin(a) / (111_320 * math.cos(math.radians(lat)))


# ---------------- geography ----------------
def kml_polygons(path, name_field):
    out = []
    for pm in ET.parse(path).getroot().findall(".//k:Placemark", NS):
        name = next((d.text for d in pm.findall(".//k:SimpleData", NS) if d.get("name") == name_field), None)
        polys = []
        for c in pm.findall(".//k:Polygon/k:outerBoundaryIs//k:coordinates", NS):
            pts = [tuple(map(float, t.split(",")[:2])) for t in c.text.split()]
            if len(pts) >= 3:
                polys.append(Polygon(pts))
        if name and polys:
            out.append((name.strip(), max(polys, key=lambda p: p.area)))
    return out


def kml_lines(path):
    lines = []
    for c in ET.parse(path).getroot().findall(".//k:LineString/k:coordinates", NS):
        pts = [tuple(map(float, t.split(",")[:2])) for t in c.text.split()]
        if len(pts) >= 2:
            lines.append(pts)
    return lines


def pune_geography(rng):
    wards = kml_polygons(ROOT / "raw/pune/pune_wards_2022.kml", "Name2")
    lines = kml_lines(ROOT / "raw/pune/pune_nalla_map.kml")
    weights = [rng.random() + 0.3 for _ in wards]  # uneven demand per ward (invented)

    def ward_of(lat, lng):
        p = Point(lng, lat)
        return next((n for n, poly in wards if poly.contains(p)), None)

    def sample(cat):
        for _ in range(200):
            if cat == "drain" and rng.random() < 0.7:
                pts = rng.choice(lines)
                i = rng.randrange(len(pts) - 1)
                t = rng.random()
                lng = pts[i][0] + t * (pts[i + 1][0] - pts[i][0])
                lat = pts[i][1] + t * (pts[i + 1][1] - pts[i][1])
                lat, lng = jitter(rng, lat, lng, 10)
            else:
                name, poly = rng.choices(wards, weights)[0]
                minx, miny, maxx, maxy = poly.bounds
                lng, lat = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                if not poly.contains(Point(lng, lat)):
                    continue
            w = ward_of(lat, lng)
            if w:
                return lat, lng, w
        raise RuntimeError("could not place a point")

    centroids = [(n, p.centroid.y, p.centroid.x) for n, p in wards]
    return sample, [n for n, _ in wards], centroids


def sandbox_geography(rng):
    lat0, lng0, step = 19.95, 73.75, 0.011  # about 1.2 km cells
    names = [f"Ward {i + 1:02d}" for i in range(30)]

    def sample(cat):
        i = rng.randrange(30)
        r, c = divmod(i, 6)
        return lat0 + (r + rng.random()) * step, lng0 + (c + rng.random()) * step, names[i]

    centroids = [(names[i], lat0 + (i // 6 + 0.5) * step, lng0 + (i % 6 + 0.5) * step) for i in range(30)]
    return sample, names, centroids


# ---------------- generation ----------------
def generate(city, prefix, n, seed, geo, langs):
    rng = random.Random(seed)
    sample, wards, _ = geo(rng)
    officers = [hashlib.sha1(f"{prefix}-officer-{i}".encode()).hexdigest()[:6] for i in range(40)]
    bad = set(rng.sample(officers, 6))
    chronic = set(rng.sample(wards, 3))
    cat_names, cat_w = list(CATS), [CATS[c][0] for c in CATS]
    month_w = [1, 1, 1, 1, 1, 3, 3, 3, 3, 1.5, 1, 1]
    photo_pool, batch_minute = [], {}
    rows = []

    def make_ticket(cat, lat, lng, ward, created, allow_spawn):
        rng_ = rng
        officer = rng_.choice(officers)
        lang = rng_.choices(list(langs), list(langs.values()))[0]
        res_h = min(lognormal(rng_, CATS[cat][1], CATS[cat][2]), MAX_RES_H)
        closed_at = created + timedelta(hours=res_h)
        row = {"ticket_id": None, "city": city, "data_quality": "synthetic", "source": "synthetic_generator",
               "category": cat, "text": TEXT[cat][lang], "lang": lang, "lat": round(lat, 6), "lng": round(lng, 6),
               "h3": h3.latlng_to_cell(lat, lng, 9), "ward": ward, "created_at": iso(created), "closed_at": "",
               "closed_by_hash": "", "status": "open", "closure_note": "", "closure_photo_id": "",
               "closure_photo_exif_dist_m": "", "gt_false_closure": "", "gt_failure_mode": "", "gt_site_changed": ""}
        if closed_at > WINDOW_END:
            return row  # still open at the end of the window
        p_false = CATS[cat][3] * (3 if officer in bad else 1) * (1.5 if ward in chronic else 1)
        false = rng_.random() < min(p_false, 0.85)
        modes = []
        if false:
            if rng_.random() < 0.5:
                closed_at = created + timedelta(hours=rng_.uniform(0.02, 0.5)); modes.append("fast_close")
            if officer in bad and rng_.random() < 0.4:
                day = closed_at.replace(hour=23, minute=58, second=0)
                if day > created:
                    closed_at = day; modes.append("batch_close")
                    batch_minute[(officer, day.date())] = True
            if rng_.random() < 0.35 and photo_pool:
                photo_id = rng_.choice(photo_pool); modes.append("photo_reuse")
            else:
                photo_id = None
            exif = rng_.uniform(300, 5000) if rng_.random() < 0.3 else abs(rng_.gauss(0, 25))
            if exif > 300:
                modes.append("wrong_location")
            modes.append("no_work")
            note = rng_.choices([None, ".", "Work completed."], [0.45, 0.15, 0.40])[0]
        else:
            photo_id, exif = None, abs(rng_.gauss(0, 25))
            note = rng_.choices([rng_.choice(GOOD_NOTES), "Work completed.", None], [0.70, 0.25, 0.05])[0]
        if photo_id is None:
            photo_id = f"ph-{prefix}-{len(photo_pool) + 1:06d}"
            photo_pool.append(photo_id)
        status = "reopened" if false and rng_.random() < 0.12 else "closed"
        row.update(closed_at=iso(closed_at), closed_by_hash=officer, status=status, closure_note=note or "",
                   closure_photo_id=photo_id, closure_photo_exif_dist_m=round(exif, 1),
                   gt_false_closure=int(false), gt_failure_mode="+".join(modes) if false else "none",
                   gt_site_changed=int(not false))
        if allow_spawn and rng_.random() < (0.60 if false else 0.08):
            when = closed_at + timedelta(days=rng_.uniform(1, 13))
            if when < WINDOW_END:
                la, ln = jitter(rng_, lat, lng, 25)
                spawned.append((cat, la, ln, ward, when))
        return row

    spawned = []
    base = []
    for _ in range(n):
        cat = rng.choices(cat_names, cat_w)[0]
        month = rng.choices(range(12), month_w if cat == "drain" else [1] * 12)[0]
        start = datetime(2024, month + 1, 1, tzinfo=timezone.utc)
        created = start + timedelta(seconds=rng.uniform(0, 28 * 86400))
        lat, lng, ward = sample(cat)
        base.append((created, cat, lat, lng, ward))
    for created, cat, lat, lng, ward in sorted(base):
        rows.append(make_ticket(cat, lat, lng, ward, created, True))
    for cat, la, ln, ward, when in sorted(spawned, key=lambda s: s[4]):
        rows.append(make_ticket(cat, la, ln, ward, when, False))
    rows.sort(key=lambda r: r["created_at"])
    for i, r in enumerate(rows, 1):
        r["ticket_id"] = f"{prefix}-{i:06d}"
    return rows


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    closed = [r for r in rows if r["status"] != "open"]
    false = [r for r in closed if r["gt_false_closure"] == 1]
    print(f"{path.name}: {len(rows)} tickets, {len(closed)} closed, {len(false)} false closures "
          f"({100 * len(false) / max(len(closed), 1):.1f}% of closed)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = ROOT / "processed"
    write(out / "synthetic_pune.csv", generate("pune", "pune", a.n, a.seed, pune_geography, {"mr": 0.55, "en": 0.25, "hi": 0.20}))
    write(out / "synthetic_city.csv", generate("synthetic", "sbx", a.n, a.seed + 1, sandbox_geography, {"en": 1.0}))
    # ward centroids for the map (Pune real polygons, sandbox grid)
    for fname, geo in (("pune_wards.csv", pune_geography), ("synthetic_wards.csv", sandbox_geography)):
        _, _, cents = geo(random.Random(0))
        with (out / fname).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ward_name", "centroid_lat", "centroid_lng"])
            w.writerows([(n, round(la, 6), round(ln, 6)) for n, la, ln in cents])
