"""A citizen who has just filed a request can read it at once, even though the Engine had cached their profile before the
request was linked. Anyone else is still refused."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import auth

SECRET = "unit-test-secret-unit-test-secret-1234"


def token(sub):
    return jwt.encode({"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 600, "email": sub + "@x"}, SECRET, algorithm="HS256")


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("AGENT_URL", "http://agent.test")
    monkeypatch.setenv("ENGINE_SERVICE_TOKEN", "svc")
    linked = {"u-a": [], "u-b": []}

    def lookup(tok):
        sub = jwt.decode(tok, options={"verify_signature": False})["sub"]
        return {"user_id": sub, "email": sub + "@x", "role": "citizen", "status": "active", "ticket_ids": list(linked[sub])}

    monkeypatch.setattr(auth, "_lookup_profile", lookup)
    auth.clear_cache()
    from app.main import app
    yield TestClient(app, raise_server_exceptions=False), linked
    auth.clear_cache()


def test_a_just_linked_ticket_is_readable_despite_a_cached_profile(setup):
    client, linked = setup
    headers = {"Authorization": "Bearer " + token("u-a")}
    assert client.get("/tickets/blr-0001", headers=headers).status_code == 403     # profile cached with no tickets
    linked["u-a"].append("blr-0001")                                                 # the Agent links it a moment later
    assert client.get("/tickets/blr-0001", headers=headers).status_code == 200      # a fresh look finds it


def test_someone_elses_ticket_stays_refused(setup):
    client, linked = setup
    linked["u-a"].append("blr-0001")
    other = {"Authorization": "Bearer " + token("u-b")}
    assert client.get("/tickets/blr-0001", headers=other).status_code == 403
    assert client.get("/tickets/blr-0001", headers=other).status_code == 403
