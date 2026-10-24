import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db.reset(":memory:")
    config.STEP_DELAY = 0
    config.OUTCOME_CHECK_DELAY = 0
    config.USE_STUBS = True
    # a developer's real .env must never make a test message a real chat or call a real LLM
    config.TELEGRAM_BOT_TOKEN = config.WHATSAPP_TOKEN = config.WHATSAPP_PHONE_NUMBER_ID = ""
    config.GEMINI_API_KEY = config.OPENAI_API_KEY = ""
    config.ENGINE_URL = "http://127.0.0.1:9"   # nothing listens here: engine calls fail fast
    yield
    db.reset()
