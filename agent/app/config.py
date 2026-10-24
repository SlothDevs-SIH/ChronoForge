"""All tunables in one place. Thresholds here must match contract/README.md."""
import os
from pathlib import Path

ENGINE_URL = os.environ.get("ENGINE_URL", "http://localhost:8001")
CONTRACT_DIR = Path(os.environ.get("CONTRACT_DIR", Path(__file__).resolve().parents[2] / "contract"))

# Verdict thresholds on posterior P(false closure)
NOT_FIXED_AT = 0.75   # posterior >= this -> likely_not_fixed
FIXED_AT = 0.25       # posterior <= this -> verified_fixed

BUDGET = int(os.environ.get("AGENT_BUDGET", "10"))
MAX_STEPS = 8
TOOL_COST = {"check_photo": 1, "check_satellite": 3, "ask_citizen": 2, "request_human_spot_check": 10}

# Seconds between steps so the UI trace is watchable in the demo. Tests set this to 0.
STEP_DELAY_S = float(os.environ.get("STEP_DELAY_S", "0.6"))
# Seconds before the post-approval outcome check (demo mode is short).
OUTCOME_DELAY_S = float(os.environ.get("OUTCOME_DELAY_S", "30"))

# LLM planner. Providers are tried in order, then the deterministic planner.
USE_LLM = os.environ.get("USE_LLM", "false").lower() == "true"
LLM_PROVIDERS = [p.strip() for p in os.environ.get("LLM_PROVIDERS", "gemini,openai").split(",") if p.strip()]
