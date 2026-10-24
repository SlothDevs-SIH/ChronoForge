import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db, http_utils  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.reset(":memory:")
    config.STEP_DELAY = 0
    config.OUTCOME_CHECK_DELAY = 0
    config.USE_STUBS = True
    # a developer's real .env must never make a test message a real chat or call a real LLM
    config.TELEGRAM_BOT_TOKEN = config.WHATSAPP_TOKEN = config.WHATSAPP_PHONE_NUMBER_ID = ""
    config.GEMINI_API_KEY = config.OPENAI_API_KEY = ""
    config.ENGINE_URL = "http://127.0.0.1:9"   # nothing listens here: engine calls fail fast
    # sign-in is off by default (the local demo); auth tests switch it on with the `auth_on` fixture
    config.AUTH_REQUIRED = False
    config.PUBLIC_DEMO_RUNS = False
    config.ADMIN_EMAILS = []
    config.ENGINE_SERVICE_TOKEN = config.ADMIN_TOKEN = ""
    config.RATE_LIMITS_ENABLED = True
    config.STORAGE_BACKEND = "local"
    config.UPLOAD_DIR = str(tmp_path / "uploads")
    config.MAX_UPLOAD_BYTES = 8 * 1024 * 1024
    http_utils.reset_rate_limits()
    yield
    _wait_for_background_runs()   # a run thread must not still be using the connection when it is closed
    db.reset()


def _wait_for_background_runs(timeout: float = 8.0) -> None:
    import threading
    import time
    end = time.time() + timeout
    while time.time() < end:
        if not [t for t in threading.enumerate() if t.name.startswith("Thread-") and t.is_alive()]:
            return
        time.sleep(0.02)


@pytest.fixture
def auth_on():
    """Sign-in switched on, verifying locally signed HS256 tokens (see tests/authkit.py)."""
    from tests.authkit import AUD, SECRET
    config.AUTH_REQUIRED = True
    config.SUPABASE_JWT_SECRET = SECRET
    config.SUPABASE_URL = ""
    config.SUPABASE_JWT_AUDIENCE = AUD
    config.REPLY_LINK_SECRET = "reply-secret-reply-secret-reply-secret"
    yield
    config.AUTH_REQUIRED = False
    config.SUPABASE_JWT_SECRET = ""
    config.REPLY_LINK_SECRET = ""


@pytest.fixture
def client(auth_on):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
