"""Run the Agent's existing CLIP check (agent/app/clip_check.py, ViT-B-32 laion2b) on the 12-ticket demo photo set.

    <exp_venv python> data/experiments/clip_demo.py        (from the repo root)

Truth = the planted plan in demo/photos/manifest.json. 12 tickets is far too few for any accuracy claim; this only shows
what the check says on each planted case. Thresholds are the hand-set ones in clip_check.py and are NOT changed here.
Writes data/experiments/clip_demo.results.json.
"""
import json
import sys
import time
from pathlib import Path

import psutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))
from app import clip_check  # noqa: E402

proc = psutil.Process()
rss0 = proc.memory_info().rss / 1e6
t0 = time.time()
emb = clip_check.OpenClipEmbedder()          # downloads the weights on first use
load_s = time.time() - t0
rss_loaded = proc.memory_info().rss / 1e6

photos = ROOT / "demo" / "photos"
manifest = json.loads((photos / "manifest.json").read_text(encoding="utf-8"))
rows, per_photo = [], []
for m in manifest:
    closure = Image.open(photos / m["after"]).convert("RGB")
    complaint = Image.open(photos / m["before"]).convert("RGB")
    t = time.time()
    flags, passed, details = clip_check.clip_checks(closure, m["category"], complaint, emb=emb)
    per_photo.append((time.time() - t))
    rows.append({"ticket": m["ticket_id"], "plan": m["plan"], "planted_failure": m["planted_failure"], "category": m["category"],
                 "flags": flags, "passed": passed, "details": details})
    print(f'{m["ticket_id"]:9} {m["plan"]:12} p_problem={details.get("scene", {}).get("p_problem_present")} '
          f'cos={details.get("before_after", {}).get("cosine")} flags={flags}')

out = {"model": "ViT-B-32 / laion2b_s34b_b79k (open_clip)", "thresholds": {"scene_still_broken": clip_check.SCENE_STILL_BROKEN, "different_place": clip_check.DIFFERENT_PLACE},
       "load_seconds": round(load_s, 1), "rss_mb_before": round(rss0), "rss_mb_after_load": round(rss_loaded), "rss_mb_peak_after_run": round(proc.memory_info().rss / 1e6),
       "seconds_per_ticket_two_images_plus_text_median": round(sorted(per_photo)[len(per_photo) // 2], 2), "rows": rows}
(ROOT / "data" / "experiments" / "clip_demo.results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
