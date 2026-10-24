"""Download openly licensed real photos from Wikimedia Commons for the demo set. Run from agent/:

    .venv/Scripts/python -m experiments.fetch_open_photos [out_dir]

Only files whose Commons licence is public domain, CC0, CC BY or CC BY-SA are kept. Each photo's author,
licence and source URL go into sources.json (attribution is a condition of CC BY / CC BY-SA, so keep that file
with the photos and credit it on the slide). No login or API key is needed.
"""
import json
import re
import sys
import time
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "TrueCloseDemo/1.0 (ayushmore27.am@gmail.com)"}
OK_LICENSE = re.compile(r"^(cc0|pd|public domain|cc[- ]by(-sa)?[- ]\d)", re.I)
# role -> Commons categories; "problem" photos show the issue, "fixed" photos show a repaired/clean surface
CATEGORIES = {
    "problem_pothole": ["Potholes"],
    "fixed_road": ["Road_resurfacing", "Newly_paved_roads", "Asphalt_roads"],
    "problem_garbage": ["Garbage_in_streets", "Litter_in_streets", "Illegal_dumping", "Waste_in_India"],
    "clean_street": ["Streets_in_India", "Clean_streets"],
}
PER_ROLE = {"problem_pothole": 14, "fixed_road": 14, "problem_garbage": 8, "clean_street": 8}


def members(client: httpx.Client, cat: str, limit: int = 60) -> list[str]:
    r = client.get(API, params={"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}",
                                "cmtype": "file", "cmlimit": limit, "format": "json"})
    return [m["title"] for m in r.json().get("query", {}).get("categorymembers", [])]


def info(client: httpx.Client, title: str) -> dict | None:
    r = client.get(API, params={"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
                                "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 960})
    page = next(iter(r.json()["query"]["pages"].values()))
    ii = (page.get("imageinfo") or [None])[0]
    if not ii or ii.get("mime") not in ("image/jpeg", "image/png"):
        return None
    meta = ii.get("extmetadata", {})
    lic = (meta.get("LicenseShortName") or {}).get("value", "")
    if not OK_LICENSE.match(lic.replace("-", " ").replace("  ", " ")) and not OK_LICENSE.match(lic):
        return None
    author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "unknown")).strip()
    return {"title": title, "license": lic, "author": author, "source": ii["descriptionurl"],
            "thumb": ii.get("thumburl") or ii["url"]}


def main(out: str = "data/open_photos"):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        for role, cats in CATEGORIES.items():
            got = 0
            for cat in cats:
                for title in members(client, cat):
                    if got >= PER_ROLE[role]:
                        break
                    meta = info(client, title)
                    if meta is None:
                        continue
                    name = f"{role}_{got:02d}.jpg"
                    try:
                        data = client.get(meta["thumb"]).content
                    except Exception:
                        continue
                    (root / name).write_bytes(data)
                    sources.append({"file": name, "role": role, "category": cat, **meta})
                    got += 1
                    time.sleep(0.3)   # be polite to Commons
            print(f"{role}: {got}")
    (root / "sources.json").write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(sources)} photos + sources.json to {root}")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
