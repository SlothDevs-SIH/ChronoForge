"""Single config file for thresholds, budget and tool costs (contract section 3)."""
import os
from dotenv import load_dotenv

load_dotenv()

# Verdict thresholds
THRESH_NOT_FIXED = 0.75   # posterior >= this -> likely_not_fixed
THRESH_FIXED = 0.25       # posterior <= this -> verified_fixed

BUDGET = 10               # total cost units per run
MAX_STEPS = 8             # hard step cap

TOOL_COSTS = {
    "get_score": 0,
    "check_photo": 1,
    "check_satellite": 3,
    "ask_citizen": 2,
    "request_human_spot_check": 10,
    "propose_action": 0,
}

# Down-weight for correlated evidence pairs (photo + citizen): ln(LR) of the weaker one is scaled
CORRELATED_PAIRS = [{"photo", "citizen"}]
CORRELATION_WEIGHT = 0.7

ENGINE_URL = os.getenv("ENGINE_URL", "http://localhost:8001")
DB_PATH = os.getenv("AGENT_DB", "agent.db")
STEP_DELAY = float(os.getenv("STEP_DELAY", "0.4"))   # seconds between steps, for a visible live trace
OUTCOME_CHECK_DELAY = float(os.getenv("OUTCOME_CHECK_DELAY", "30"))  # demo mode: 30 s
PHOTO_INDEX_PATH = os.getenv("PHOTO_INDEX", "data/photo_index.json")
USE_STUBS = os.getenv("AGENT_USE_STUBS", "1") == "1"  # stub tools until real services are wired
