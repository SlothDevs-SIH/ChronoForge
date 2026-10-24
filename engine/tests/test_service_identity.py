"""The Agent calls the Engine with X-Service-Token: it may read tickets, scores and run checks, nothing else."""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("ENGINE_SERVICE_TOKEN", "svc-secret")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AGENT_URL", "http://agent.invalid")
    auth.clear_cache()
    yield TestClient(app)
    auth.clear_cache()


def test_service_token_reads_tickets_and_scores(client):
    h = {"X-Service-Token": "svc-secret"}
    assert client.get("/tickets", headers=h, params={"limit": 1}).status_code == 200
    assert client.get("/tickets/blr-0001", headers=h).status_code in (200, 404)     # allowed to ask; 404 only if the id is absent
    assert client.get("/tickets/blr-0001/score", headers=h).status_code in (200, 404)


def test_wrong_or_missing_service_token_is_refused(client):
    assert client.get("/tickets", headers={"X-Service-Token": "nope"}).status_code == 401
    assert client.get("/tickets").status_code == 401


def test_service_token_does_not_open_admin_sync(client):
    r = client.post("/connectors/mumbai/sync", headers={"X-Service-Token": "svc-secret"})
    assert r.status_code in (401, 403)
