# Usage: python web/scripts/make_hero_video.py <repo root> <path to ffmpeg>   (pip install imageio-ffmpeg gives you an ffmpeg binary)
"""Process the AI-generated hero video: hide its garbled baked-in text, strip the audio, write web assets.
The source file is never modified.

The camera is locked off, so:
  A, B  the two generated cards (they appear at 0.95 s and 6.8 s) are replaced with a CLEAN PLATE: the first frame, taken
        before any card exists. The city simply continues; no visible box.
  C, D, E  elements that are baked into EVERY frame (bottom bar of garbled icon labels, logo with a garbled tagline, the
        baked headline) have no clean plate, so they are softly frosted. The real brand lockup and headline are HTML.
All patches have feathered edges. Regions are in source pixels (1280x720), found from a 0.5 s contact sheet.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
FF = str(Path(sys.argv[2]))
SRC = str(ROOT / "frontend_comp" / "gemini_generated_video_11b95b20.mp4")
OUT = ROOT / "web" / "public" / "assets" / "hero"
OUT.mkdir(parents=True, exist_ok=True)
PLATE = OUT / "plate.png"

REGIONS = [  # name, kind, x, y, w, h, start_seconds (None = always); all even
    ("A", "plate", 400, 120, 380, 420, 0.95),
    ("B", "plate", 796, 140, 310, 336, 6.8),
    ("C", "blur", 20, 610, 1240, 106, None),
    ("D", "blur", 12, 18, 300, 134, None),
    ("E", "blur", 6, 168, 462, 174, None),
]
FEATHER = 18
DURATION = 10.0


def graph() -> str:
    n_blur = sum(r[1] == "blur" for r in REGIONS)
    n_plate = sum(r[1] == "plate" for r in REGIONS)
    parts = [f"[0:v]split={n_blur + 1}[base0]" + "".join(f"[s{i}]" for i in range(n_blur)),
             f"[1:v]format=yuva420p,split={n_plate}" + "".join(f"[pl{i}]" for i in range(n_plate))]
    last, bi, pi = "base0", 0, 0
    for k, (name, kind, x, y, w, h, start) in enumerate(REGIONS):
        if kind == "blur":
            parts.append(f"[s{bi}]crop={w}:{h}:{x}:{y},gblur=sigma=22:steps=3,eq=brightness=0.05:saturation=0.85,format=yuva420p[p{k}]")
            bi += 1
        else:
            parts.append(f"[pl{pi}]crop={w}:{h}:{x}:{y}[p{k}]")
            pi += 1
        r = min(FEATHER - 3, h // 4 - 1)
        parts.append(f"color=c=black:s={w}x{h}:d={DURATION + 0.2},drawbox=x={FEATHER}:y={FEATHER}:w={w - 2 * FEATHER}:h={h - 2 * FEATHER}:color=white:t=fill,"
                     f"boxblur={r}:2,format=gray,scale=in_range=limited:out_range=full[m{k}]")
        parts.append(f"[p{k}][m{k}]alphamerge[f{k}]")
        enable = f":enable='gte(t,{start})'" if start is not None else ""
        parts.append(f"[{last}][f{k}]overlay={x}:{y}{enable}[base{k + 1}]")
        last = f"base{k + 1}"
    parts.append(f"[{last}]format=yuv420p[out]")
    return ";".join(parts)


def run(*args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "warning", "-y", *args], check=True)


run("-ss", "0", "-i", SRC, "-frames:v", "1", "-update", "1", str(PLATE))            # the clean plate
(OUT / "graph.txt").write_text(graph(), encoding="utf-8")
inputs = ["-i", SRC, "-loop", "1", "-t", str(DURATION), "-i", str(PLATE), "-/filter_complex", str(OUT / "graph.txt"), "-map", "[out]", "-an"]
run(*inputs, "-t", str(DURATION), "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-r", "24", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(OUT / "hero.mp4"))
run(*inputs, "-frames:v", "1", "-q:v", "3", "-update", "1", str(OUT / "hero-poster.jpg"))
(OUT / "graph.txt").unlink()
PLATE.unlink()
for f in ("hero.mp4", "hero-poster.jpg"):
    print(f, round((OUT / f).stat().st_size / 1024), "KB")
