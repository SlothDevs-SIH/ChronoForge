"""Single config file for thresholds, budget and tool costs (contract section 3)."""
import os
from pathlib import Path
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

REPO_ROOT = Path(os.getenv("REPO_ROOT", Path(__file__).resolve().parents[2]))
ENGINE_URL = os.getenv("ENGINE_URL", "http://localhost:8001")
DB_PATH = os.getenv("AGENT_DB", "agent.db")
STEP_DELAY = float(os.getenv("STEP_DELAY", "0.4"))   # seconds between steps, for a visible live trace
OUTCOME_CHECK_DELAY = float(os.getenv("OUTCOME_CHECK_DELAY", "30"))  # demo mode: 30 s
SATELLITE_TIMEOUT = float(os.getenv("SATELLITE_TIMEOUT", "120"))  # a live Sentinel-2 read takes 20 to 60 s; cached answers are instant
# With real services (AGENT_USE_STUBS=0) an unreachable Engine or an unknown ticket must fail loudly, never invent a stub prior.
ALLOW_STUB_FALLBACK = os.getenv("AGENT_ALLOW_STUB_FALLBACK", "0") == "1"
PHOTO_INDEX_PATH = os.getenv("PHOTO_INDEX", "data/photo_index.json")
USE_STUBS = os.getenv("AGENT_USE_STUBS", "1") == "1"  # stub tools until real services are wired
USE_CLIP = os.getenv("AGENT_USE_CLIP", "0") == "1"    # needs torch + open_clip_torch and a ~400 MB download
USE_SKEPTIC = os.getenv("AGENT_USE_SKEPTIC", "0") == "1"
USE_VISION_LLM = os.getenv("AGENT_USE_VISION_LLM", "0") == "1"   # sends photos to Gemini: demo photos only
USE_DINO = os.getenv("AGENT_USE_DINO", "0") == "1"      # DINOv2-small before/after matching (needs transformers + torch)
USE_LLM_PLANNER = os.getenv("AGENT_USE_LLM_PLANNER", "0") == "1"

# LLM providers tried in order, then the deterministic planner. Keys live in .env only.
LLM_PROVIDERS = [p.strip() for p in os.getenv("LLM_PROVIDERS", "gemini,openai").split(",") if p.strip()]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "8"))   # a bot reply must not wait long on a slow LLM

# When set, endpoints that message people, approve actions or read local files need header X-Admin-Token.
ADMIN_TOKEN = os.getenv("AGENT_ADMIN_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_POLLING = os.getenv("TELEGRAM_POLLING", "0") == "1"   # long-poll instead of a webhook
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
