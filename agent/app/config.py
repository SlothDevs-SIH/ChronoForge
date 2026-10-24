"""Single config file for thresholds, budget and tool costs (contract section 3).

The verification numbers (thresholds, budget, costs, every likelihood ratio) live in verification_config.json, which is
versioned. Nothing here may change them without a deliberate new version; tests pin the v1 values.
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---- versioned verification config -----------------------------------------------------------------------------
VC_PATH = Path(__file__).resolve().parent / "verification_config.json"
VC: dict = json.loads(VC_PATH.read_text(encoding="utf-8"))
CONFIG_VERSION: str = VC["version"]
CALIBRATED: bool = bool(VC["calibrated"])        # False while the likelihood ratios are unmeasured configured priors
CALIBRATION_NOTE: str = VC["note"]

# Verdict thresholds
THRESH_NOT_FIXED = VC["thresholds"]["not_fixed"]   # posterior >= this -> likely_not_fixed
THRESH_FIXED = VC["thresholds"]["fixed"]           # posterior <= this -> verified_fixed

BUDGET = VC["budget"]               # total cost units per run
MAX_STEPS = VC["max_steps"]         # hard step cap

TOOL_COSTS = dict(VC["tool_costs"])

# Down-weight for correlated evidence pairs (photo + citizen): ln(LR) of the weaker one is scaled
CORRELATED_PAIRS = [set(p) for p in VC["correlation"]["pairs"]]
CORRELATION_WEIGHT = VC["correlation"]["weight"]

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


# ---- auth, roles, hosting (contract/AUTH_AND_DEPLOY.md) --------------------------------------------------------
def _csv(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0") == "1"   # 0 keeps the local demo open (treated as a local admin)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
ADMIN_EMAILS = [e.lower() for e in _csv("ADMIN_EMAILS")]
CORS_ORIGINS = _csv("CORS_ORIGINS")                      # empty = "*" (local only)
PUBLIC_DEMO_RUNS = os.getenv("PUBLIC_DEMO_RUNS", "0") == "1"
ENGINE_SERVICE_TOKEN = os.getenv("ENGINE_SERVICE_TOKEN", "")
REPLY_LINK_SECRET = os.getenv("REPLY_LINK_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")             # Postgres when set; otherwise SQLite at DB_PATH
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"       # read the client address from X-Forwarded-For (behind Render)
RATE_LIMITS_ENABLED = os.getenv("RATE_LIMITS_ENABLED", "1") == "1"

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # local | supabase
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "evidence")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
SIGNED_URL_SECONDS = int(os.getenv("SIGNED_URL_SECONDS", "300"))

# ---- case tracking, citizen photos, silence handling (website requests) ----------------------------------------
WATCH_INTERVAL = float(os.getenv("AGENT_WATCH_INTERVAL", "15"))   # seconds between looks for newly closed tracked tickets; 0 = off
PHOTO_DIR = os.getenv("AGENT_PHOTO_DIR", "data/citizen_photos")   # photos citizens send in the bot chat (resized, EXIF removed)
MAX_PHOTO_BYTES = int(os.getenv("AGENT_MAX_PHOTO_BYTES", str(8 * 1024 * 1024)))
REMINDER_HOURS = float(os.getenv("AGENT_REMINDER_HOURS", "24"))   # remind once after this long without an answer
ESCALATE_HOURS = float(os.getenv("AGENT_ESCALATE_HOURS", "48"))   # then send the case to a person
REQUESTS_PER_HOUR = int(os.getenv("AGENT_REQUESTS_PER_HOUR", "10"))   # requests one citizen may file per hour
