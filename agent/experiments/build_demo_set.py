"""Build the committed demo photo set from the Commons downloads. Run from agent/ after fetch_open_photos:

    .venv/Scripts/python -m experiments.build_demo_set

Writes ../demo/photos/ (repo root, where the Engine fixtures point):
  <ticket>-closure.jpg        closure photos for the contract fixture tickets
  planted/DEMO-xxx_*.jpg      before/after pairs with planted failures + manifest.json
  ATTRIBUTION.md              author, licence and source for every real photo (CC BY / CC BY-SA require this)

Real: the photo content (open licences). Synthetic and labelled so in the manifest: EXIF GPS/time written onto
the photos, the planted failures, and the photos for categories with no open source (streetlight, drain).
"""
import json
import shutil
from pathlib import Path

from PIL import Image

from experiments.make_demo_photos import exif, scene

SRC = Path("data/open_photos")
OUT = Path("../demo/photos")
POTHOLE_OK = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13]   # 00 is a bus, 07 a manhole: not potholes
FIXED_OK = [0, 1, 2, 4, 5, 9, 10, 11, 12]               # finished smooth asphalt, no equipment or defect
GARBAGE_OK = [0, 1, 3]
CLEAN_OK = [1, 6]
CLOSED = "2026-10-21T09:00:00Z"
GOOD_TIME = "2026:10:20 10:00:00"


def load(role: str, i: int) -> Image.Image:
    im = Image.open(SRC / f"{role}_{i:02d}.jpg").convert("RGB")
    im.thumbnail((720, 720))
    return im


def save(im: Image.Image, path: Path, lat=None, lng=None, taken=GOOD_TIME):
    path.parent.mkdir(parents=True, exist_ok=True)
    if lat is None:
        im.save(path, quality=82)
    else:
        im.save(path, quality=82, exif=exif(lat, lng, taken))


def main():
    if not SRC.exists():
        raise SystemExit("run experiments.fetch_open_photos first")
    sources = {s["file"]: s for s in json.loads((SRC / "sources.json").read_text(encoding="utf-8"))}
    used: list[str] = []
    manifest = []

    def real(role, i):
        used.append(f"{role}_{i:02d}.jpg")
        return load(role, i)

    # 1. fixture tickets (contract/tickets.json): closure photos named <ticket>-closure.jpg
    fixtures = [("blr-0001", 12.9352, 77.6245, "fixed_road", FIXED_OK[0]),
                ("blr-0002", 12.9716, 77.5946, "clean_street", CLEAN_OK[1]),
                ("mum-0001", 19.076, 72.8777, "fixed_road", FIXED_OK[1])]
    for tid, lat, lng, role, i in fixtures:
        save(real(role, i), OUT / f"{tid}-closure.jpg", lat, lng)
    for tid, lat, lng in (("blr-0003", 12.925, 77.5938), ("pune-0001", 18.5204, 73.8567)):   # no open source
        save(scene(sum(map(ord, tid)), False), OUT / f"{tid}-closure.jpg", lat, lng)

    # 2. planted-failure pairs (potholes)
    plan = ["clean"] * 3 + ["reused"] * 2 + ["shifted_gps"] * 2 + ["stale_time"] * 2 + ["still_broken"] * 2
    befores, fixed = list(POTHOLE_OK[:11]), list(FIXED_OK[2:])
    spare_pothole = POTHOLE_OK[11]
    clean_afters: list[Path] = []
    for n, kind in enumerate(plan):
        tid, lat, lng = f"DEMO-{n:03d}", 12.90 + n * 0.002, 77.55 + n * 0.002
        d = OUT / "planted"
        save(real("problem_pothole", befores[n]), d / f"{tid}_before.jpg", lat, lng, "2026:10:01 10:00:00")
        after = d / f"{tid}_after.jpg"
        a_lat, a_lng, taken = lat, lng, GOOD_TIME
        if kind == "reused":
            shutil.copy(clean_afters[n - 3], after)         # the same closure photo on another ticket
        else:
            if kind == "shifted_gps":
                a_lat, a_lng = lat + 0.1, lng + 0.1          # about 15 km away
            if kind == "stale_time":
                taken = "2026:05:01 10:00:00"
            if kind == "still_broken":
                src = ("problem_pothole", spare_pothole) if n == 9 else ("problem_pothole", befores[n])
                img = real(*src)
            else:
                img = real("fixed_road", fixed.pop(0))
            save(img, after, a_lat, a_lng, taken)
            if kind == "clean":
                clean_afters.append(after)
        manifest.append({"ticket_id": tid, "category": "pothole", "lat": lat, "lng": lng, "closed_at": CLOSED,
                         "before": f"planted/{tid}_before.jpg", "after": f"planted/{tid}_after.jpg",
                         "plan": kind, "planted_failure": kind != "clean",
                         "label": "Photo content: real, open licence (see ATTRIBUTION.md). "
                                  "EXIF location/time and the planted failure: synthetic demo data."})

    # 3. one garbage pair (real) so the demo is not potholes only
    save(real("problem_garbage", GARBAGE_OK[0]), OUT / "planted" / "DEMO-g00_before.jpg", 12.97, 77.59,
         "2026:10:01 10:00:00")
    save(real("clean_street", CLEAN_OK[0]), OUT / "planted" / "DEMO-g00_after.jpg", 12.97, 77.59)
    manifest.append({"ticket_id": "DEMO-g00", "category": "garbage", "lat": 12.97, "lng": 77.59,
                     "closed_at": CLOSED, "before": "planted/DEMO-g00_before.jpg",
                     "after": "planted/DEMO-g00_after.jpg", "plan": "clean", "planted_failure": False,
                     "label": "real open-licence photos, synthetic EXIF"})

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lines = ["# Demo photo attribution", "",
             "Real photos come from Wikimedia Commons under the licences below (attribution is required for CC BY "
             "and CC BY-SA). They were resized and had EXIF location/time written onto them for the demo. "
             "`blr-0003-closure.jpg`, `pune-0001-closure.jpg` and any file with a drawn pothole blob are "
             "synthetic placeholders.", "",
             "| Our file role | Author | Licence | Source |", "|---|---|---|---|"]
    for name in sorted(set(used)):
        s = sources[name]
        lines.append(f"| {name} | {s['author'][:60]} | {s['license']} | {s['source']} |")
    (OUT / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(manifest)} planted tickets, {len(set(used))} real photos used, wrote {OUT.resolve()}")


if __name__ == "__main__":
    main()
