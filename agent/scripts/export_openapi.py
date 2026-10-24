"""Write agent/openapi.json from the running app definition: python scripts/export_openapi.py (from agent/)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import app  # noqa: E402

out = Path(__file__).resolve().parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("wrote", out, "with", len(app.openapi()["paths"]), "paths")
