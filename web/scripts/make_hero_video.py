"""Build the landing-page hero video from frontend_comp/gemini_generated_video_28ed53ce.mp4. The source is never modified.

The whole 10 second clip is kept at its original speed. The only edit is removing the generator's sparkle watermark, a
translucent four-point star at about (1160, 600) in the 1280x720 frame, with ffmpeg's removelogo filter and a mask
drawn here. Output: hero.mp4 (H.264), hero.webm (VP9), hero-poster.jpg (first frame), 720p, no audio.

Usage: python web/scripts/make_hero_video.py <repo root> <ffmpeg path>
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(sys.argv[1])
FF = str(Path(sys.argv[2]))
SRC = str(ROOT / "frontend_comp" / "gemini_generated_video_28ed53ce.mp4")
OUT = ROOT / "web" / "public" / "assets" / "hero"
OUT.mkdir(parents=True, exist_ok=True)

CX, CY, R = 1160, 600, 27          # watermark centre and arm length


def star_mask(path: Path) -> None:
    """White four-point star (slightly grown) on black, same size as the video."""
    img = Image.new("L", (1280, 720), 0)
    pts = [(CX, CY - R), (CX + 6, CY - 6), (CX + R, CY), (CX + 6, CY + 6),
           (CX, CY + R), (CX - 6, CY + 6), (CX - R, CY), (CX - 6, CY - 6)]
    ImageDraw.Draw(img).polygon(pts, fill=255)
    img = img.filter(ImageFilter.MaxFilter(13))      # grow by 6 px so the star's soft edge is covered too
    img.save(path)


def run(*args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "warning", "-y", *args], check=True)


mask = OUT / "watermark_mask.png"
star_mask(mask)
clean = f"removelogo=f={mask.as_posix()},scale=1280:720,format=yuv420p"
run("-i", SRC, "-an", "-vf", clean, "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-r", "24",
    "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(OUT / "hero.mp4"))
run("-i", SRC, "-an", "-vf", clean, "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", "0", "-row-mt", "1", "-r", "24",
    str(OUT / "hero.webm"))
run("-i", str(OUT / "hero.mp4"), "-frames:v", "1", "-q:v", "3", "-update", "1", str(OUT / "hero-poster.jpg"))
mask.unlink()
for f in ("hero.mp4", "hero.webm", "hero-poster.jpg"):
    print(f, round((OUT / f).stat().st_size / 1024), "KB")
