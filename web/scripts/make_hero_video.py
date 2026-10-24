"""Build the landing-page hero loop from frontend_comp/gemini_generated_video_28ed53ce.mp4. The source is never modified.

The source is AI-generated. Its middle shows UI cards, a slide and a monitor whose text is garbled, so only the clean
aerial city shot at the end (8.45-10.0 s, a slow push-in) is used. The two small labelled tags in that shot are covered
with a patch cloned from the scenery just above them, and the generator's sparkle mark in the bottom-right corner is
blurred. The shot is played forward then backward, which makes a seamless loop, and slowed 2x. Audio is dropped.

Usage: python web/scripts/make_hero_video.py <repo root> <ffmpeg path>
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
FF = str(Path(sys.argv[2]))
SRC = str(ROOT / "frontend_comp" / "gemini_generated_video_28ed53ce.mp4")
OUT = ROOT / "web" / "public" / "assets" / "hero"
OUT.mkdir(parents=True, exist_ok=True)

A0, A1 = 8.45, 10.0
SLOW = 2.0
# Soft patches (x, y, w, h, from-second, clone offset). Clone offset: copy from this many px up; None blurs instead.
PATCHES = [(880, 236, 240, 120, 8.3, -120), (1118, 556, 100, 100, None, None)]
FEATHER = 22


def graph() -> str:
    pre = [f"[0:v]split={len(PATCHES) + 1}[base0]" + "".join(f"[c{i}]" for i in range(len(PATCHES)))]
    last = "base0"
    for i, (x, y, w, h, start, dy) in enumerate(PATCHES):
        if dy is None:
            pre.append(f"[c{i}]crop={w}:{h}:{x}:{y},gblur=sigma=14:steps=3,format=yuva420p[p{i}]")
        else:   # clone nearby scenery over the tag; the camera moves slowly so a fixed offset stays plausible
            pre.append(f"[c{i}]crop={w}:{h}:{x}:{y + dy},format=yuva420p[p{i}]")
        # feathered mask: the blur radius must stay under the interior size or the centre never reaches full opacity
        pre.append(f"color=c=black:s={w}x{h}:d=10.2,drawbox=x={FEATHER}:y={FEATHER}:w={w - 2 * FEATHER}:h={h - 2 * FEATHER}:color=white:t=fill,"
                   f"boxblur={FEATHER // 3}:2,format=gray,scale=in_range=limited:out_range=full[m{i}]")
        pre.append(f"[p{i}][m{i}]alphamerge[f{i}]")
        enable = f":enable='gte(t,{start})'" if start is not None else ""
        pre.append(f"[{last}][f{i}]overlay={x}:{y}{enable}[base{i + 1}]")
        last = f"base{i + 1}"
    return ";".join(pre + [
        f"[{last}]trim={A0}:{A1},setpts=PTS-STARTPTS,fps=24,split=2[fwd][rev0]",
        "[rev0]reverse[rev]",
        "[fwd][rev]concat=n=2:v=1:a=0[both]",
        f"[both]setpts={SLOW}*PTS,minterpolate=fps=24:mi_mode=blend,scale=1280:720,format=yuv420p[out]",
    ])


def run(*args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "warning", "-y", *args], check=True)


g = OUT / "graph.txt"
g.write_text(graph(), encoding="utf-8")
run("-i", SRC, "-/filter_complex", str(g), "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "26",
    "-r", "24", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(OUT / "hero.mp4"))
run("-i", str(OUT / "hero.mp4"), "-frames:v", "1", "-q:v", "3", "-update", "1", str(OUT / "hero-poster.jpg"))
g.unlink()
for f in ("hero.mp4", "hero-poster.jpg"):
    print(f, round((OUT / f).stat().st_size / 1024), "KB")
