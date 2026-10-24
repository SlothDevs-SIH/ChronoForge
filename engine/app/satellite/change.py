"""Change of a site compared with matched control windows. Pure numpy/scipy, no network.

Why controls: raw "change" means nothing. Seasons, monsoon vegetation and sensor differences change every pixel between
two dates. So the question is "did THIS site change more than similar places nearby did?"

Controls are windows from the same scenes that LOOKED LIKE the site before (matched on NDVI, NDBI and brightness),
so a dump site is compared with other built-up patches, not with a park. The statistic is the change magnitude over four
index differences, expressed against the controls' own spread, and reported as a percentile among the controls.
It is undirected: it says the site changed unusually, not what changed.
"""
import numpy as np
from scipy.ndimage import uniform_filter

from .reader import SCL_INVALID

FEATURES = ("ndvi", "ndbi", "ndwi", "bright")
MATCH_FEATURES = ("ndvi", "ndbi", "bright")
SIGMA_FLOOR = np.array([0.01, 0.01, 0.01, 0.005])   # index units: stops a near-constant control set from exploding z


def _nd(a, b):
    return (a - b) / np.maximum(a + b, 1e-6)


def indices(refl: np.ndarray) -> dict[str, np.ndarray]:
    blue, green, red, nir, swir = refl
    return {"ndvi": _nd(nir, red), "ndbi": _nd(swir, nir), "ndwi": _nd(green, nir), "bright": (blue + green + red) / 3.0}


def valid_mask(refl_b, refl_a, scl_b, scl_a) -> np.ndarray:
    return (~np.isin(scl_b, SCL_INVALID)) & (~np.isin(scl_a, SCL_INVALID)) & (refl_b.sum(0) > 0) & (refl_a.sum(0) > 0)


def _wmean(values: np.ndarray, valid: np.ndarray, size: int):
    num = uniform_filter(np.where(valid, values, 0.0), size=size, mode="constant")
    den = uniform_filter(valid.astype(float), size=size, mode="constant")
    return num / np.maximum(den, 1e-9), den


def window_stats(refl_b, refl_a, scl_b, scl_a, half: int) -> dict[str, np.ndarray]:
    """Per-pixel statistics of the (2*half+1)-square window centred there, over pixels clear in BOTH scenes."""
    size = 2 * half + 1
    valid = valid_mask(refl_b, refl_a, scl_b, scl_a)
    ib, ia = indices(refl_b), indices(refl_a)
    out: dict[str, np.ndarray] = {}
    den = None
    for f in FEATURES:
        mb, den = _wmean(ib[f], valid, size)
        ma, _ = _wmean(ia[f], valid, size)
        out["b_" + f], out["d_" + f] = mb, ma - mb
    out["valid"] = den
    return out


def detect_stats(site: np.ndarray, ctrl: np.ndarray) -> dict:
    """site: (4,) index differences of the site; ctrl: (n,4) of the controls. Percentile of the site's change magnitude."""
    med = np.median(ctrl, 0)
    sig = np.maximum(1.4826 * np.median(np.abs(ctrl - med), 0), SIGMA_FLOOR)
    zc, zs = (ctrl - med) / sig, (site - med) / sig
    s_c, s_s = np.sqrt((zc ** 2).mean(1)), float(np.sqrt((zs ** 2).mean()))
    pct = float((s_c < s_s).mean() + 0.5 * (s_c == s_s).mean())
    mad = 1.4826 * np.median(np.abs(s_c - np.median(s_c)))
    return {"percentile": round(pct, 4), "z_score": round(float((s_s - np.median(s_c)) / max(mad, 1e-6)), 3),
            "site_score": round(s_s, 3), "feature_z": {f: round(float(v), 2) for f, v in zip(FEATURES, zs)},
            "site_delta": {f: round(float(v), 4) for f, v in zip(FEATURES, site)},
            "control_sigma": {f: round(float(v), 4) for f, v in zip(FEATURES, sig)}}


def analyse(refl_b, refl_a, scl_b, scl_a, site_half: int = 6, stride: int = 10, min_dist: int = 25,
            n_controls: int = 60, min_valid: float = 0.7, min_controls: int = 20) -> dict:
    """The site is the centre of the arrays. Returns detect_stats plus bookkeeping, or {"abstain": reason}."""
    h, w = scl_b.shape
    cy, cx = h // 2, w // 2
    st = window_stats(refl_b, refl_a, scl_b, scl_a, site_half)
    site_valid = float(st["valid"][cy, cx])
    if site_valid < min_valid:
        return {"abstain": "the site is cloud-obscured or has no data in one of the two scenes", "site_valid": round(site_valid, 3)}
    ys, xs = np.arange(site_half, h - site_half, stride), np.arange(site_half, w - site_half, stride)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    yy, xx = yy.ravel(), xx.ravel()
    ok = (np.hypot(yy - cy, xx - cx) >= min_dist) & (st["valid"][yy, xx] >= min_valid)
    yy, xx = yy[ok], xx[ok]
    if len(yy) < min_controls:
        return {"abstain": f"only {len(yy)} clear comparison windows (need {min_controls})", "site_valid": round(site_valid, 3)}
    base = np.stack([st["b_" + f][yy, xx] for f in MATCH_FEATURES], 1)
    site_base = np.array([st["b_" + f][cy, cx] for f in MATCH_FEATURES])
    scale = np.maximum(1.4826 * np.median(np.abs(base - np.median(base, 0)), 0), 0.02)
    dist = np.sqrt((((base - site_base) / scale) ** 2).sum(1))
    pick = np.argsort(dist)[:n_controls]
    ctrl = np.stack([st["d_" + f][yy[pick], xx[pick]] for f in FEATURES], 1)
    site = np.array([st["d_" + f][cy, cx] for f in FEATURES])
    out = detect_stats(site, ctrl)
    out.update(n_controls=int(len(pick)), n_candidates=int(len(yy)), site_valid=round(site_valid, 3),
               match_distance_median=round(float(np.median(dist[pick])), 2),
               _site=site, _controls=ctrl)   # kept for the validation (private keys, stripped before caching)
    return out
