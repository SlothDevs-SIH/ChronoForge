"""Generate a labelled SYNTHETIC demo photo set with planted failures. Run from agent/:

    .venv/Scripts/python -m experiments.make_demo_photos [out_dir]

These are textured placeholders, not real pothole or garbage photos, and are labelled demo data in
manifest.json. Swap the files for licence-clean real photos (same names) before the final demo.
Planted failures: reused photo, shifted GPS, stale timestamp, still-broken scene.
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

LAT, LNG = 12.9716, 77.5946   # Bengaluru centre; tickets get small offsets


def scene(seed: int, broken: bool, size=(256, 256)) -> Image.Image:
    rnd = random.Random(seed)
    base = rnd.randrange(90, 140)
    img = Image.new("RGB", size, (base, base, base))
    d = ImageDraw.Draw(img)
    for _ in range(400):                       # asphalt grain, unique per seed so hashes differ
        x, y, g = rnd.randrange(size[0]), rnd.randrange(size[1]), rnd.randrange(60, 170)
        d.point((x, y), (g, g, g))
    for _ in range(6):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        c = rnd.randrange(40, 200)
        d.rectangle([x, y, x + rnd.randrange(20, 70), y + rnd.randrange(10, 50)], fill=(c, c - 10, c - 20))
    if broken:                                  # dark pothole blob
        cx, cy = size[0] // 2 + rnd.randrange(-30, 30), size[1] // 2 + rnd.randrange(-30, 30)
        d.ellipse([cx - 45, cy - 30, cx + 45, cy + 30], fill=(20, 18, 16))
    return img


def exif(lat: float, lng: float, taken: str) -> Image.Exif:
    ex = Image.Exif()
    ex[0x8825] = {1: "N" if lat >= 0 else "S", 2: (abs(lat), 0, 0), 3: "E" if lng >= 0 else "W", 4: (abs(lng), 0, 0)}
    ex[0x0132] = taken
    return ex


def main(out: str = "data/photos", n: int = 24):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    plans = (["clean"] * 12 + ["reused"] * 4 + ["shifted_gps"] * 3 + ["stale_time"] * 2 + ["still_broken"] * 3)[:n]
    clean_after: list[Path] = []
    for i, plan in enumerate(plans):
        tid = f"DEMO-{i:03d}"
        lat, lng = LAT + i * 0.001, LNG + i * 0.001
        closed = "2026-10-21T09:00:00Z"
        before, after = root / f"{tid}_before.jpg", root / f"{tid}_after.jpg"
        scene(i, True).save(before)
        taken, a_lat, a_lng = "2026:10:20 10:00:00", lat, lng
        if plan == "shifted_gps":
            a_lat, a_lng = lat + 0.1, lng + 0.1          # ~15 km away
        if plan == "stale_time":
            taken = "2026:05:01 10:00:00"
        if plan == "reused" and clean_after:
            after.write_bytes(clean_after[i % len(clean_after)].read_bytes())   # same image, other ticket
        else:
            scene(1000 + i, plan == "still_broken").save(after, exif=exif(a_lat, a_lng, taken))
            if plan == "clean":
                clean_after.append(after)
        manifest.append({"ticket_id": tid, "lat": lat, "lng": lng, "closed_at": closed, "category": "pothole",
                         "before": before.name, "after": after.name, "planted_failure": plan != "clean",
                         "plan": plan, "data_quality": "synthetic", "label": "DEMO DATA, not real municipal photos"})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} tickets to {root}")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
