"""Windowed Sentinel-2 L2A reads from the public cloud-optimised GeoTIFFs. Only the requested window is downloaded.

Conventions follow our earlier GEOAI-04 project (see NOTICE.md): five bands (blue, green, red, nir, swir1 resampled to
10 m), the DN offset decided from the pixels, and the scene classification layer (SCL) for masking.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import numpy as np
import rasterio
import rasterio.errors
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

for _k, _v in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
               "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "2", "GDAL_HTTP_TIMEOUT": "60"}.items():
    os.environ.setdefault(_k, _v)

# At most this many simultaneous reads from the archive across ALL callers. The first validation run let three checks read
# 6 bands each in parallel: a quarter of them failed with "Read failed", which was our load, not the satellites.
_CONNECTIONS = threading.BoundedSemaphore(int(os.environ.get("SAT_MAX_CONNECTIONS", "6")))
READ_ATTEMPTS = 6

SCL_INVALID = (0, 1, 3, 8, 9, 10)   # no data, saturated, cloud shadow, cloud medium, cloud high, cirrus
BAND_ASSETS = ("blue", "green", "red", "nir", "swir16")   # order of the reflectance stack


@dataclass
class Window:
    refl: np.ndarray            # [5, H, W] reflectance 0..1.5 (blue, green, red, nir, swir1)
    scl: np.ndarray             # [H, W] scene classification
    transform: object
    crs: str
    dn_offset: int


def context_bbox(lat: float, lng: float, half_m: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) in degrees for a square of side 2*half_m metres around a point."""
    dlat = half_m / 111_320.0
    dlng = half_m / (111_320.0 * np.cos(np.radians(lat)))
    return lng - dlng, lat - dlat, lng + dlng, lat + dlat


def _open(href: str, attempts: int = 4):
    for i in range(attempts):
        try:
            return rasterio.open(href)
        except rasterio.errors.RasterioIOError:
            if i == attempts - 1:
                raise
            time.sleep(2 ** i)


def detect_offset(baseline: str, blue_dn: np.ndarray) -> int:
    """DN offset to remove, decided from the pixels (processing baseline 04.00+ defines (DN - 1000) / 10000, but some
    scenes in the archive already had it applied and the metadata does not say reliably which)."""
    if baseline < "04.00":
        return 0
    v = blue_dn[blue_dn > 0]
    return 1000 if v.size and np.percentile(v, 1) >= 1000 else 0


def _grid(href: str, bbox_ll):
    with _CONNECTIONS, _open(href) as ref:
        b = transform_bounds("EPSG:4326", ref.crs, *bbox_ll)
        win = from_bounds(*b, ref.transform).round_offsets().round_lengths()
        return b, (int(win.height), int(win.width)), ref.window_transform(win), str(ref.crs)


def _read_band(href: str, b, shape, resampling, attempts: int = READ_ATTEMPTS) -> np.ndarray:
    """Read one window, retrying with backoff: the bucket occasionally fails a read even after a successful open.
    The connection slot is released while waiting, so a retrying read never blocks the others."""
    for i in range(attempts):
        try:
            with _CONNECTIONS, _open(href) as s:
                return s.read(1, window=from_bounds(*b, s.transform), out_shape=shape, resampling=resampling,
                              boundless=True, fill_value=0)
        except rasterio.errors.RasterioIOError:
            if i == attempts - 1:
                raise
            time.sleep(min(2 ** i, 20))


def read_scl(scl_href: str, red_href: str, bbox_ll) -> np.ndarray:
    """Cheap cloud check: only the scene classification layer over a small box."""
    b, shape, _, _ = _grid(red_href, bbox_ll)
    return _read_band(scl_href, b, shape, Resampling.nearest)


def read_window(hrefs: dict[str, str], baseline: str, bbox_ll, workers: int = 6) -> Window:
    """hrefs: asset name -> URL for blue, green, red, nir, swir16, scl."""
    b, shape, transform, crs = _grid(hrefs["red"], bbox_ll)
    jobs = [(hrefs[a], Resampling.bilinear) for a in BAND_ASSETS] + [(hrefs["scl"], Resampling.nearest)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        raw = list(pool.map(lambda j: _read_band(j[0], b, shape, j[1]), jobs))
    bands, scl = [a.astype(np.float32) for a in raw[:5]], raw[5]
    offset = detect_offset(baseline, bands[0])
    refl = np.stack([np.clip((a - offset) / 10000.0, 0, 1.5) for a in bands])
    return Window(refl=refl, scl=scl, transform=transform, crs=crs, dn_offset=offset)
