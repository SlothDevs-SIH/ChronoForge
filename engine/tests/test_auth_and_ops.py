"""Permission matrix, token checks, error envelope, /ready, CORS allowlist, warehouse bootstrap and demo-ingest idempotency.

Tokens are signed locally with HS256; the Agent's role lookup (`GET /auth/me`) is replaced by a table of personas."""
import functools
import http.server
import importlib
import io
import json
import tarfile
import threading
import time
from pathlib import Path

import httpx
import jwt
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import auth, bootstrap

SECRET = "unit-test-secret-unit-test-secret-1234"
SERVICE = "svc-token"

PERSONAS = {
    "citizen": {"user_id": "u-cit", "email": "c@x", "role": "citizen", "status": "active", "ticket_ids": ["blr-0001"]},
    "officer": {"user_id": "u-off", "email": "o@x", "role": "officer", "status": "active", "ticket_ids": []},
    "admin": {"user_id": "u-adm", "email": "a@x", "role": "admin", "status": "active", "ticket_ids": []},
    "pending_officer": {"user_id": "u-pen", "email": "p@x", "role": "officer", "status": "pending", "ticket_ids": []},
    "rejected": {"user_id": "u-rej", "email": "r@x", "role": "officer", "status": "rejected", "ticket_ids": []},
}


def token_for(sub: str, **over) -> str:
    claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 600, "email": sub + "@x"}
    claims.update(over)
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("AGENT_URL", "http://agent.test")
    monkeypatch.setenv("ENGINE_SERVICE_TOKEN", SERVICE)
    monkeypatch.delenv("ENGINE_ADMIN_TOKEN", raising=False)
    by_sub = {p["user_id"]: p for p in PERSONAS.values()}
    calls = []

    def fake_lookup(token: str) -> dict:
        calls.append(token)
        return by_sub[jwt.decode(token, options={"verify_signature": False})["sub"]]

    monkeypatch.setattr(auth, "_lookup_profile", fake_lookup)
    auth.clear_cache()
    from app.main import app
    c = TestClient(app, raise_server_exceptions=False)
    c.lookup_calls = calls
    yield c
    auth.clear_cache()


def hdr(persona: str | None) -> dict:
    return {} if persona is None else {"Authorization": "Bearer " + token_for(PERSONAS[persona]["user_id"])}


def ok(resp) -> bool:
    """Authentication and authorisation let the request through (the endpoint itself may still answer 404 or 409)."""
    return resp.status_code not in (401, 403, 503)


ALL = [None, "citizen", "officer", "admin", "pending_officer", "rejected"]
ALLOWED = {
    # (method, path): who gets through
    ("GET", "/health"): ALL,
    ("GET", "/ready"): ALL,
    ("GET", "/cities"): ALL,
    ("GET", "/eval/results"): ALL,
    ("GET", "/media/demo/nope/before.jpg"): ALL,
    ("GET", "/tickets"): ["officer", "admin"],
    ("GET", "/wards/stats"): ["officer", "admin"],
    ("GET", "/wards/map?city=bengaluru"): ["officer", "admin"],
    ("POST", "/satellite/check"): ["officer", "admin"],
    ("GET", "/tickets/blr-0001"): ["citizen", "officer", "admin"],           # the citizen's linked ticket
    ("GET", "/tickets/blr-0001/score"): ["citizen", "officer", "admin"],
    ("GET", "/satellite/chip/blr-0001/before.png"): ["citizen", "officer", "admin"],
    ("GET", "/tickets/blr-0002"): ["officer", "admin"],                      # not linked to the citizen
    ("GET", "/tickets/blr-0002/score"): ["officer", "admin"],
    ("GET", "/satellite/chip/blr-0002/after.png"): ["officer", "admin"],
    ("POST", "/connectors/atlantis/sync"): ["admin"],
}


@pytest.mark.parametrize("method,path", list(ALLOWED))
@pytest.mark.parametrize("persona", ALL)
def test_permission_matrix(client, method, path, persona):
    body = {"json": {"ticket_id": "blr-0001"}} if method == "POST" and path == "/satellite/check" else {}
    r = client.request(method, path, headers=hdr(persona), **body)
    assert ok(r) == (persona in ALLOWED[(method, path)]), (method, path, persona, r.status_code, r.text[:120])
    if not ok(r):
        assert r.status_code == (401 if persona is None else 403)


def test_muni_needs_the_service_token_and_nothing_else(client):
    path = "/muni/tickets"
    assert client.get(path).status_code == 403
    for persona in ("citizen", "officer", "admin"):
        assert client.get(path, headers=hdr(persona)).status_code == 403          # no user role reaches the municipal system
    assert client.get(path, headers={"X-Service-Token": "wrong"}).status_code == 403
    assert client.get(path, headers={"X-Service-Token": SERVICE}).status_code == 200
    assert client.post("/muni/tickets/nope/reopen").status_code == 403
    assert client.post("/muni/tickets/nope/reopen", headers={"X-Service-Token": SERVICE}).status_code == 404   # passed auth


def test_muni_fails_closed_when_the_service_token_is_unset(client, monkeypatch):
    monkeypatch.delenv("ENGINE_SERVICE_TOKEN")
    assert client.get("/muni/tickets", headers={"X-Service-Token": "anything"}).status_code == 503


def test_admin_token_still_works_for_connector_sync(client, monkeypatch):
    monkeypatch.setenv("ENGINE_ADMIN_TOKEN", "s3cret")
    assert client.post("/connectors/atlantis/sync", headers={"X-Admin-Token": "s3cret"}).status_code == 404   # passed auth
    assert client.post("/connectors/atlantis/sync", headers={"X-Admin-Token": "nope"}).status_code == 401


@pytest.mark.parametrize("bad", [
    "Bearer not-a-jwt",
    "Basic abc",
    "Bearer " + jwt.encode({"sub": "u-adm", "aud": "authenticated", "exp": int(time.time()) - 5}, SECRET, algorithm="HS256"),   # expired
    "Bearer " + jwt.encode({"sub": "u-adm", "aud": "someone-else", "exp": int(time.time()) + 600}, SECRET, algorithm="HS256"),   # audience
    "Bearer " + jwt.encode({"sub": "u-adm", "aud": "authenticated", "exp": int(time.time()) + 600}, "another-secret-another-secret-12", algorithm="HS256"),
    "Bearer " + jwt.encode({"sub": "u-adm", "aud": "authenticated"}, SECRET, algorithm="HS256"),   # no exp
])
def test_bad_tokens_are_401(client, bad):
    r = client.get("/tickets", headers={"Authorization": bad})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_unsigned_alg_none_token_is_refused(client):
    none_token = jwt.encode({"sub": "u-adm", "aud": "authenticated", "exp": int(time.time()) + 600}, key=None, algorithm="none")
    assert client.get("/tickets", headers={"Authorization": "Bearer " + none_token}).status_code == 401


def test_agent_unreachable_is_503_never_access(client, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.undo()            # drop the fake lookup, keep nothing else assumed
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("AGENT_URL", "http://agent.test")
    monkeypatch.setattr(auth.httpx, "get", down)
    auth.clear_cache()
    r = client.get("/tickets", headers=hdr("admin"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"


def test_missing_agent_url_is_503(client, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.delenv("AGENT_URL", raising=False)
    auth.clear_cache()
    assert client.get("/tickets", headers=hdr("admin")).status_code == 503


def test_asymmetric_tokens_are_verified_against_the_jwks(client, monkeypatch):
    """Production Supabase projects sign with ES256 and publish a JWKS; verify that path with a locally generated key."""
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())

    class FakeJWKS:
        def __init__(self, url, **kw):
            self.url = url

        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.delenv("SUPABASE_JWT_SECRET")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(auth.jwt, "PyJWKClient", FakeJWKS)
    monkeypatch.setattr(auth, "_jwk_client", None)
    good = jwt.encode({"sub": "u-off", "aud": "authenticated", "exp": int(time.time()) + 600}, key, algorithm="ES256")
    other = jwt.encode({"sub": "u-off", "aud": "authenticated", "exp": int(time.time()) + 600}, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
    auth.clear_cache()
    assert client.get("/tickets", headers={"Authorization": "Bearer " + good}).status_code == 200
    assert client.get("/tickets", headers={"Authorization": "Bearer " + other}).status_code == 401
    assert auth._jwk_client.url == "https://proj.supabase.co/auth/v1/.well-known/jwks.json"


def test_role_lookup_is_cached(client):
    h = hdr("officer")
    for _ in range(3):
        assert client.get("/tickets", headers=h).status_code == 200
    assert len(client.lookup_calls) == 1


def test_auth_off_keeps_the_laptop_demo_open(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    from app.main import app
    c = TestClient(app)
    assert c.get("/tickets").status_code == 200 and c.get("/muni/tickets").status_code == 200


# ---- error envelope, request ids, /ready ----
def test_error_envelope_and_request_id(client):
    r = client.get("/tickets/nope", headers={**hdr("admin"), "X-Request-ID": "abc123"})
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "unknown ticket nope"}, "request_id": "abc123"}
    assert r.headers["x-request-id"] == "abc123"
    v = client.get("/tickets", params={"min_score": 7}, headers=hdr("admin"))
    assert v.status_code == 422 and v.json()["error"]["code"] == "validation_error" and v.json()["request_id"]
    u = client.get("/tickets")
    assert u.status_code == 401 and set(u.json()) == {"error", "request_id"} and u.headers["content-type"].startswith("application/json")
    assert client.get("/health").headers["x-request-id"]      # generated when the caller sends none


def test_unhandled_errors_are_json_500(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.store, "cities", lambda: 1 / 0)
    r = client.get("/cities")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error" and "division" not in r.text


def test_ready_reports_store_state(client):
    r = client.get("/ready")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["ready"] is True and body["store_loaded"] is True and body["mode"] == "fixtures" and "warehouse_files" in body


def test_ready_is_503_when_fixtures_run_where_a_warehouse_is_expected(client, monkeypatch):
    monkeypatch.delenv("ENGINE_DATA_MODE")        # fixtures mode only counts as ready when it was asked for
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["ready"] is False and r.json()["reason"]


def test_cors_allowlist(monkeypatch):
    from app import main
    monkeypatch.setenv("CORS_ORIGINS", "https://good.example")
    try:
        importlib.reload(main)
        c = TestClient(main.app)
        good = c.get("/health", headers={"Origin": "https://good.example"})
        bad = c.get("/health", headers={"Origin": "https://evil.example"})
        assert good.headers.get("access-control-allow-origin") == "https://good.example"
        assert "access-control-allow-origin" not in bad.headers
    finally:
        monkeypatch.delenv("CORS_ORIGINS")
        importlib.reload(main)


# ---- warehouse bootstrap ----
def _tar(path: Path, entries: dict[str, bytes], prefix: str = "") -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def _parquet_bytes() -> bytes:
    buf = io.BytesIO()
    pd.DataFrame({"ticket_id": ["x-1"], "city": ["pune"]}).to_parquet(buf, index=False)
    return buf.getvalue()


@pytest.mark.parametrize("prefix", ["", "./", "warehouse/"])
def test_safe_extract_handles_common_layouts(tmp_path, prefix):
    arc = _tar(tmp_path / "w.tar.gz", {"tickets_x.parquet": b"data", "scores_x.parquet": b"s"}, prefix)
    n = bootstrap.safe_extract(arc, tmp_path / "out")
    assert n == 2 and (tmp_path / "out" / "tickets_x.parquet").read_bytes() == b"data"


@pytest.mark.parametrize("name", ["../evil.txt", "ok/../../evil.txt", "/abs/evil.txt"])
def test_safe_extract_rejects_traversal(tmp_path, name):
    arc = tmp_path / "bad.tar.gz"
    with tarfile.open(arc, "w:gz") as tf:
        info = tarfile.TarInfo(name)
        info.size = 4
        tf.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(ValueError, match="unsafe path"):
        bootstrap.safe_extract(arc, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_safe_extract_rejects_links(tmp_path):
    arc = tmp_path / "link.tar.gz"
    with tarfile.open(arc, "w:gz") as tf:
        info = tarfile.TarInfo("tickets_x.parquet")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)
    with pytest.raises(ValueError, match="links and devices"):
        bootstrap.safe_extract(arc, tmp_path / "out")


@pytest.fixture
def archive_server(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield served, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_fetch_warehouse_downloads_and_unpacks(tmp_path, archive_server):
    served, base = archive_server
    _tar(served / "warehouse.tar.gz", {"tickets_pune.parquet": _parquet_bytes()})
    n = bootstrap.fetch_warehouse(base + "/warehouse.tar.gz", tmp_path / "wh")
    assert n == 1 and bootstrap.has_warehouse(tmp_path / "wh")


def test_fetch_warehouse_raises_on_http_error(tmp_path, archive_server):
    _, base = archive_server
    with pytest.raises(httpx.HTTPStatusError):
        bootstrap.fetch_warehouse(base + "/missing.tar.gz", tmp_path / "wh")


def test_prepare_fetches_once_then_leaves_an_existing_warehouse_alone(tmp_path, archive_server, monkeypatch, capsys):
    served, base = archive_server
    _tar(served / "warehouse.tar.gz", {"tickets_pune.parquet": _parquet_bytes()})
    wh = tmp_path / "wh"
    monkeypatch.setattr(bootstrap, "warehouse_dir", lambda: wh)
    monkeypatch.setenv("WAREHOUSE_URL", base + "/warehouse.tar.gz")
    bootstrap.prepare()
    assert (wh / "tickets_pune.parquet").exists() and (wh / "tickets_demo.parquet").exists()
    monkeypatch.setenv("WAREHOUSE_URL", base + "/definitely-not-there.tar.gz")     # a second start must not fetch again
    bootstrap.prepare()
    assert "unpacked" not in capsys.readouterr().out.split("demo ingest")[-1]


def test_prepare_without_a_url_or_warehouse_starts_in_fixtures_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "warehouse_dir", lambda: tmp_path / "empty")
    monkeypatch.delenv("WAREHOUSE_URL", raising=False)
    bootstrap.prepare()
    assert "fixtures mode" in capsys.readouterr().out


# ---- demo ingest idempotency ----
def test_demo_ingest_is_idempotent_and_keeps_status_overrides(tmp_path):
    from app.ingest import SOURCES, ingest
    d = tmp_path / "wh"
    first = ingest(SOURCES["demo"](), d)
    overrides = d / "status_overrides.json"
    overrides.write_text(json.dumps({"DEMO-003": "reopened"}))
    second = ingest(SOURCES["demo"](), d)
    third = ingest(SOURCES["demo"](), d)
    assert len(first) == len(second) == len(third) == 12
    assert first.equals(second) and first.equals(third)
    assert len(pd.read_parquet(d / "tickets_demo.parquet")) == 12
    assert json.loads(overrides.read_text()) == {"DEMO-003": "reopened"}      # approved reopens survive a redeploy
    assert sorted(p.name for p in d.iterdir() if p.suffix == ".parquet") == ["tickets_demo.parquet", "truth_demo.parquet"]   # same files every run
    assert len(set(first["ticket_id"])) == 12                                   # no duplicate rows
