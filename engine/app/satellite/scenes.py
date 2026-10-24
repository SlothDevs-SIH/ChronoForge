"""Scene search and before/after pair selection.

A pair must come from the SAME Sentinel-2 tile (same pixel grid and viewing geometry). "before" is the latest clear
scene before the complaint was filed; "after" is the earliest clear scene after it was closed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np
from pystac_client import Client

from . import reader

STAC_URL = "https://earth-search.aws.element84.com/v1"
BEFORE_DAYS, AFTER_DAYS = 60, 60          # how far from the ticket we are willing to look for a scene
MAX_SCENE_CLOUD = 70.0                    # whole-tile cloud %, only a coarse prefilter: the site is checked with SCL
SITE_MIN_VALID = 0.80                     # share of clear pixels around the site required in each scene
CANDIDATES_PER_SIDE = 4


@dataclass
class Scene:
    id: str
    when: datetime
    tile: str
    cloud: float
    baseline: str
    hrefs: dict

    def brief(self) -> dict:
        return {"id": self.id, "date": self.when.date().isoformat(), "tile": self.tile, "tile_cloud_pct": round(self.cloud, 1)}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _to_scene(item) -> Optional[Scene]:
    p = item.properties
    assets = {k: item.assets[k].href for k in ("blue", "green", "red", "nir", "swir16", "scl") if k in item.assets}
    if len(assets) < 6:
        return None
    return Scene(id=item.id, when=_parse(p["datetime"]), tile=str(p.get("grid:code") or p.get("s2:mgrs_tile") or ""),
                 cloud=float(p.get("eo:cloud_cover", 100)), baseline=str(p.get("s2:processing_baseline", "00.00")), hrefs=assets)


def search(lat: float, lng: float, start: datetime, end: datetime, client: Optional[Client] = None) -> list[Scene]:
    client = client or Client.open(STAC_URL)
    d = 0.0005
    res = client.search(collections=["sentinel-2-l2a"], bbox=[lng - d, lat - d, lng + d, lat + d],
                        datetime=f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                        query={"eo:cloud_cover": {"lt": MAX_SCENE_CLOUD}}, max_items=120)
    return [s for s in (_to_scene(i) for i in res.items()) if s]


def site_valid_fraction(scene: Scene, lat: float, lng: float, half_m: float = 130) -> float:
    scl = reader.read_scl(scene.hrefs["scl"], scene.hrefs["red"], reader.context_bbox(lat, lng, half_m))
    return float(1 - np.isin(scl, reader.SCL_INVALID).mean())


def choose_pair(lat: float, lng: float, created: datetime, closed: datetime, client: Optional[Client] = None,
                valid_fn: Callable[[Scene], float] = None) -> tuple[Optional[Scene], Optional[Scene], str]:
    """Returns (before, after, note). note is empty on success, otherwise the reason there is no usable pair."""
    client = client or Client.open(STAC_URL)
    before = search(lat, lng, created - timedelta(days=BEFORE_DAYS), created, client)
    after = search(lat, lng, closed, closed + timedelta(days=AFTER_DAYS), client)
    if not before:
        return None, None, f"no Sentinel-2 scene in the {BEFORE_DAYS} days before the complaint was filed"
    if not after:
        return None, None, f"no Sentinel-2 scene in the {AFTER_DAYS} days after the closure"
    valid_fn = valid_fn or (lambda s: site_valid_fraction(s, lat, lng))
    tiles = sorted({s.tile for s in before} & {s.tile for s in after})
    if not tiles:
        return None, None, "before and after scenes come from different tiles (different pixel grids)"
    best = None
    for tile in tiles:
        b_c = sorted([s for s in before if s.tile == tile], key=lambda s: created - s.when)[:CANDIDATES_PER_SIDE]
        a_c = sorted([s for s in after if s.tile == tile], key=lambda s: s.when - closed)[:CANDIDATES_PER_SIDE]
        b = next((s for s in b_c if valid_fn(s) >= SITE_MIN_VALID), None)
        a = next((s for s in a_c if valid_fn(s) >= SITE_MIN_VALID), None)
        if b and a:
            gap = (created - b.when) + (a.when - closed)
            if best is None or gap < best[0]:
                best = (gap, b, a)
    if best is None:
        return None, None, "the site is cloud-obscured in every nearby before or after scene"
    return best[1], best[2], ""
