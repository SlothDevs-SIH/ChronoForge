"""Container entrypoint: `python -m app.bootstrap`.

1. If WAREHOUSE_DIR has no tickets_*.parquet and WAREHOUSE_URL is set, download that .tar.gz and unpack it safely.
2. Run the demo ingest (idempotent: it replaces tickets_demo.parquet with identical rows and never touches
   status_overrides.json, so approved reopens survive a redeploy).
3. Start uvicorn on $PORT.

The warehouse (about 28 MB) is not baked into the image and is not in git: build it with `python -m app.ingest all`,
pack it with `tar -czf warehouse.tar.gz -C data/warehouse .` and host it at a private URL.
"""
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

import httpx


def warehouse_dir() -> Path:
    # Same rule as store.WAREHOUSE_DIR, but NOT imported from there: importing app.store builds the store at once, and
    # at this point the warehouse has not been downloaded yet, so the service would stay stuck in fixtures mode.
    root = Path(__file__).resolve().parents[2]
    return Path(os.environ.get("WAREHOUSE_DIR", root / "data" / "warehouse"))


def has_warehouse(directory: Path) -> bool:
    return directory.exists() and any(directory.glob("tickets_*.parquet"))


def safe_extract(archive: Path, dest: Path) -> int:
    """Unpack a .tar.gz into dest. Refuses absolute paths, '..' segments, links and device files. A single top-level
    folder shared by every member is stripped, so both `./x.parquet` and `warehouse/x.parquet` layouts work."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    count = 0
    with tarfile.open(archive, "r:*") as tf:
        members = [m for m in tf.getmembers() if m.name not in (".", "./")]
        for m in members:
            parts = Path(m.name).parts
            if m.name.startswith(("/", "\\")) or Path(m.name).is_absolute() or ".." in parts:
                raise ValueError(f"unsafe path in archive: {m.name!r}")
            if not (m.isfile() or m.isdir()):
                raise ValueError(f"unsupported entry in archive (links and devices are refused): {m.name!r}")
        tops = {Path(m.name).parts[0] for m in members if Path(m.name).parts and Path(m.name).parts[0] != "."}
        strip = len(tops) == 1 and all(len(Path(m.name).parts) > 1 or m.isdir() for m in members)
        for m in members:
            parts = [x for x in Path(m.name).parts if x != "."]
            if strip:
                parts = parts[1:]
            if not parts:
                continue
            target = (root.joinpath(*parts)).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe path in archive: {m.name!r}")
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


def fetch_warehouse(url: str, dest: Path) -> int:
    """Stream the archive to a temp file (never into memory), then unpack. Raises on any HTTP or archive problem."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "warehouse.tar.gz"
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)) as r:
            r.raise_for_status()
            with open(archive, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        return safe_extract(archive, dest)


def run_demo_ingest(directory: Path) -> int:
    from .ingest import SOURCES, ingest
    return len(ingest(SOURCES["demo"](), directory))


def prepare() -> None:
    d = warehouse_dir()
    url = os.environ.get("WAREHOUSE_URL", "")
    if not has_warehouse(d):
        if not url:
            print("bootstrap: no warehouse and WAREHOUSE_URL is not set; the Engine will start in fixtures mode", flush=True)
            return
        print(f"bootstrap: fetching the warehouse into {d}", flush=True)
        n = fetch_warehouse(url, d)
        print(f"bootstrap: unpacked {n} files", flush=True)
    print(f"bootstrap: demo ingest, {run_demo_ingest(d)} demo tickets", flush=True)


def main() -> None:
    try:
        prepare()
    except Exception as exc:   # a failed fetch must be visible; the service then starts and /ready reports 503
        print(f"bootstrap: warehouse preparation failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    import uvicorn   # in-process (not exec): works the same on Linux and Windows, and uvicorn handles SIGTERM itself
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8001")), log_level="info")


if __name__ == "__main__":
    main()
