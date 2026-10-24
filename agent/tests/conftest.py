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
    config.ENGINE_URL = "http://127.0.0.1:9"   # nothing listens here: engine calls fail fast
    yield
    db.reset()
