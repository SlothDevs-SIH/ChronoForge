"""Permission matrix: every endpoint in contract/AUTH_AND_DEPLOY.md against every kind of caller, with locally signed tokens.

A caller is "denied" when the answer is 401 (no token) or 403 with a permission error code. Anything else (200, 404 for
an unknown id, 409, 422) means the request got past the permission check.
"""
import json
import time

import pytest

from app import config
from app.db import get_conn
from app.models import now_iso
from tests.authkit import bearer, jpeg_bytes, link, make_token, seed_user

WHO = ["anon", "citizen", "linked", "pending", "rejected", "officer", "admin"]
ALL = set(WHO)
SIGNED = ALL - {"anon"}
ACTIVE = {"citizen", "linked", "officer", "admin"}
STAFF = {"officer", "admin"}
ADMIN = {"admin"}
TICKET_ACCESS = {"linked", "officer", "admin"}
DENY_CODES = {"unauthorized", "forbidden", "account_not_active"}


@pytest.fixture
def world(client):
    """Users of every kind plus a finished run, an uploaded photo and a reply link for ticket T-100."""
    seed_user("u_citizen")
    seed_user("u_linked")
    link("u_linked", "T-100")
    seed_user("u_pending", "officer", "pending", "officer")
    seed_user("u_rejected", "citizen", "rejected")
    seed_user("u_officer", "officer")
    seed_user("u_admin", "admin")
    seed_user("u_target")
    get_conn().execute("INSERT INTO runs (run_id, ticket_id, status, trace, created_at) VALUES ('run-1','T-100','done','[]',?)",
                       (now_iso(),))
    get_conn().commit()
    up = client.post("/tickets/T-100/evidence/photo", headers=bearer("u_officer"),
                     files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
    assert up.status_code == 200, up.text
    link_resp = client.post("/citizen/reply-links", headers=bearer("u_officer"), json={"ticket_id": "T-100"})
    assert link_resp.status_code == 200, link_resp.text
    return {"evidence_id": up.json()["evidence_id"], "token": link_resp.json()["token"]}


def headers_for(who: str) -> dict:
    return {} if who == "anon" else bearer({"citizen": "u_citizen", "linked": "u_linked", "pending": "u_pending",
                                            "rejected": "u_rejected", "officer": "u_officer", "admin": "u_admin"}[who])


def endpoints(w: dict):
    photo = lambda: {"files": {"file": ("a.jpg", jpeg_bytes(gps=False), "image/jpeg")}}
    return [
        ("GET /health", "GET", "/health", {}, ALL),
        ("GET /ready", "GET", "/ready", {}, ALL),
        ("GET /auth/me", "GET", "/auth/me", {}, SIGNED),
        ("POST /auth/profile", "POST", "/auth/profile", {"json": {"requested_role": "citizen"}}, ACTIVE),
        ("GET /me/tickets", "GET", "/me/tickets", {}, ACTIVE),
        ("POST /agent/run", "POST", "/agent/run/T-100", {}, STAFF),
        ("GET /agent/stream", "GET", "/agent/stream/run-1", {}, STAFF),
        ("GET /agent/runs", "GET", "/agent/runs/run-1", {}, STAFF),
        ("GET /approvals", "GET", "/approvals", {}, STAFF),
        ("POST /approvals/decide", "POST", "/approvals/nope/decide", {"json": {"decision": "reject"}}, STAFF),
        ("GET /audit", "GET", "/audit", {}, STAFF),
        ("GET /audit/verify", "GET", "/audit/verify", {}, STAFF),
        ("GET /outcomes", "GET", "/outcomes", {}, STAFF),
        ("GET /verification list", "GET", "/verification/T-100", {}, TICKET_ACCESS),
        ("GET /verification latest", "GET", "/verification/T-100/latest", {}, TICKET_ACCESS),
        ("GET /admin/users", "GET", "/admin/users", {}, ADMIN),
        ("POST /admin approve", "POST", "/admin/users/u_target/approve", {}, ADMIN),
        ("POST /admin reject", "POST", "/admin/users/u_target/reject", {}, ADMIN),
        ("POST /admin role", "POST", "/admin/users/u_target/role", {"json": {"role": "citizen"}}, ADMIN),
        ("POST /admin link", "POST", "/admin/users/u_target/tickets", {"json": {"ticket_id": "T-100"}}, ADMIN),
        ("DELETE /admin link", "DELETE", "/admin/users/u_target/tickets/T-100", {}, ADMIN),
        ("POST /citizen/reply-links", "POST", "/citizen/reply-links", {"json": {"ticket_id": "T-100"}}, STAFF),
        ("GET /reply", "GET", f"/reply/{w['token']}", {}, ALL),
        ("POST /reply", "POST", f"/reply/{w['token']}", {"json": {"answer": "yes"}}, ALL),
        ("POST /evidence photo upload", "POST", "/tickets/T-100/evidence/photo", photo(), TICKET_ACCESS),
        ("GET /tickets evidence list", "GET", "/tickets/T-100/evidence", {}, TICKET_ACCESS),
        ("GET /evidence url", "GET", f"/evidence/{w['evidence_id']}/url", {}, TICKET_ACCESS),
        ("POST /citizen contact", "POST", "/citizen/T-100/contact", {"json": {"chat_id": "1"}}, STAFF),
        ("POST /citizen/send", "POST", "/citizen/send", {"json": {"ticket_id": "T-100"}}, STAFF),
        ("POST /citizen ask", "POST", "/citizen/T-100/ask", {"json": {}}, STAFF),
        ("POST /evidence/photo", "POST", "/evidence/photo",
         {"json": {"ticket_id": "T-100", "closure_photo_url": "demo/nonexistent-photo.jpg"}}, STAFF),
        ("POST /telegram/webhook", "POST", "/telegram/webhook", {"json": {"update_id": 1}}, ALL),
    ]


def _cases():
    names = [e[0] for e in endpoints({"token": "x", "evidence_id": "x"})]
    return [(n, who) for n in names for who in WHO]


@pytest.mark.parametrize("name,who", _cases(), ids=[f"{n}|{w}" for n, w in _cases()])
def test_permission_matrix(client, world, name, who):
    spec = next(e for e in endpoints(world) if e[0] == name)
    _, method, path, kw, allowed = spec
    r = client.request(method, path, headers=headers_for(who), **kw)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    body = body if isinstance(body, dict) else {}
    code = (body.get("error") or {}).get("code")
    denied = r.status_code == 401 or (r.status_code == 403 and code in DENY_CODES)
    if who in allowed:
        assert not denied, f"{who} should be allowed on {name} but got {r.status_code} {body}"
    else:
        assert denied, f"{who} should be denied on {name} but got {r.status_code} {body}"
        assert r.status_code == (401 if who == "anon" else 403), (r.status_code, body)
        assert body["error"]["code"] and body["request_id"] == r.headers["x-request-id"]


# ---- specifics beyond the matrix --------------------------------------------------------------------------------------
def test_citizen_sees_only_linked_tickets(client, world):
    h = bearer("u_linked")
    assert client.get("/verification/T-100/latest", headers=h).status_code == 200
    assert client.get("/verification/T-200/latest", headers=h).status_code == 403
    assert client.get("/tickets/T-200/evidence", headers=h).status_code == 403
    r = client.post("/tickets/T-200/evidence/photo", headers=h, files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 403
    assert client.get("/me/tickets", headers=h).json() == [{"ticket_id": "T-100"}]


def test_pending_and_rejected_users_can_only_read_their_profile(client, world):
    for sub, status in (("u_pending", "pending"), ("u_rejected", "rejected")):
        me = client.get("/auth/me", headers=bearer(sub))
        assert me.status_code == 200 and me.json()["status"] == status
        for path in ("/approvals", "/audit", "/me/tickets", "/admin/users"):
            r = client.get(path, headers=bearer(sub))
            assert r.status_code == 403 and r.json()["error"]["code"] in DENY_CODES, (sub, path)


def test_bad_tokens_are_401_with_the_error_shape(client, world):
    cases = {
        "expired": make_token("u_officer", expires_in=-60),
        "wrong secret": make_token("u_officer", secret="another-secret-another-secret-another-1"),
        "wrong audience": make_token("u_officer", aud="somebody-else"),
        "garbage": "not.a.token",
    }
    for label, tok in cases.items():
        r = client.get("/approvals", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, label
        assert r.json()["error"]["code"] in ("token_expired", "invalid_token"), (label, r.json())
        assert r.json()["request_id"] == r.headers["x-request-id"]
    assert client.get("/approvals", headers={"Authorization": "Basic abc"}).status_code == 401


def test_unsigned_alg_none_token_is_refused(client, world):
    import base64
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    tok = f"{b({'alg': 'none', 'typ': 'JWT'})}.{b({'sub': 'u_admin', 'aud': 'authenticated', 'exp': int(time.time()) + 600})}."
    assert client.get("/audit", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_admin_emails_bootstrap_needs_a_confirmed_email(client):
    config.ADMIN_EMAILS = ["boss@example.test"]
    unconfirmed = client.get("/auth/me", headers=bearer("u_x1", email="boss@example.test", confirmed=False))
    assert unconfirmed.json()["role"] == "citizen"
    stranger = client.get("/auth/me", headers=bearer("u_x2", email="nobody@example.test"))
    assert stranger.json()["role"] == "citizen"
    boss = client.get("/auth/me", headers=bearer("u_x3", email="Boss@Example.test"))
    assert boss.json() == {"user_id": "u_x3", "email": "boss@example.test", "role": "admin", "status": "active",
                           "requested_role": None, "ticket_ids": []}
    # an existing citizen whose confirmed email is later added to the list is promoted on the next call
    config.ADMIN_EMAILS.append("late@example.test")
    assert client.get("/auth/me", headers=bearer("u_x4", email="late@example.test")).json()["role"] == "admin"


def test_officer_signup_is_pending_until_an_admin_approves(client):
    h = bearer("u_new", email="new.officer@example.test")
    assert client.get("/auth/me", headers=h).json()["role"] == "citizen"
    r = client.post("/auth/profile", headers=h, json={"requested_role": "officer"})
    assert r.status_code == 200 and (r.json()["role"], r.json()["status"]) == ("officer", "pending")
    assert client.get("/approvals", headers=h).status_code == 403          # pending grants nothing
    seed_user("u_admin", "admin")
    assert client.post("/admin/users/u_new/approve", headers=bearer("u_admin")).json()["status"] == "active"
    assert client.get("/approvals", headers=h).status_code == 200
    # an approved officer cannot change their own role through the profile endpoint
    assert client.post("/auth/profile", headers=h, json={"requested_role": "citizen"}).status_code == 409


def test_admin_can_reject_set_roles_and_link_tickets_and_it_is_audited(client):
    seed_user("u_admin", "admin")
    seed_user("u_pend", "officer", "pending", "officer")
    seed_user("u_cit")
    a = bearer("u_admin")
    assert client.post("/admin/users/u_pend/reject", headers=a).json()["status"] == "rejected"
    assert client.get("/approvals", headers=bearer("u_pend")).status_code == 403
    assert client.post("/admin/users/u_cit/role", headers=a, json={"role": "officer"}).json()["role"] == "officer"
    assert client.post("/admin/users/u_admin/role", headers=a, json={"role": "citizen"}).status_code == 409   # no lock-out
    linked = client.post("/admin/users/u_cit/tickets", headers=a, json={"ticket_id": "MUM-1"}).json()
    assert linked["ticket_ids"] == ["MUM-1"]
    assert client.post("/admin/users/u_cit/tickets", headers=a, json={"ticket_id": "bad id!"}).status_code == 422
    assert client.delete("/admin/users/u_cit/tickets/MUM-1", headers=a).json()["ticket_ids"] == []
    assert client.post("/admin/users/nobody/approve", headers=a).status_code == 404
    listed = client.get("/admin/users?status=pending", headers=a).json()
    assert listed == []
    kinds = [e["event"]["type"] for e in client.get("/audit", headers=a).json()]
    assert {"user_rejected", "user_role_set", "ticket_linked", "ticket_unlinked"} <= set(kinds)
    assert client.get("/audit/verify", headers=a).json()["ok"] is True


def test_decide_records_who_decided(client):
    from app import approvals
    from app.models import Verdict
    seed_user("u_officer", "officer")
    v = Verdict(ticket_id="T-9", state="likely_not_fixed", prior=0.5, posterior=0.9, evidence_ids=[],
                recommended_action="reopen", requires_human=True, explanation="x")
    a = approvals.propose_action("T-9", None, "reopen", v)
    assert client.post(f"/approvals/{a['approval_id']}/decide", json={"decision": "approve"}).status_code == 401
    r = client.post(f"/approvals/{a['approval_id']}/decide", headers=bearer("u_officer"),
                    json={"decision": "reject", "note": "photo is fine"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "rejected" and body["note"] == "photo is fine"
    assert body["actor"] == "u_officer" and body["actor_email"] == "u_officer@example.test" and body["decided_at"]
    decided = [e for e in client.get("/audit", headers=bearer("u_officer")).json() if e["event"]["type"] == "approval_decided"]
    assert decided[-1]["event"]["actor"] == "u_officer" and decided[-1]["event"]["note"] == "photo is fine"
    # semantics unchanged: a second decision is a conflict
    assert client.post(f"/approvals/{a['approval_id']}/decide", headers=bearer("u_officer"),
                       json={"decision": "approve"}).status_code == 409


def test_public_demo_runs_only_open_demo_tickets_to_anonymous_callers(client):
    assert client.post("/agent/run/DEMO-001").status_code == 401          # off by default
    config.PUBLIC_DEMO_RUNS = True
    ok = client.post("/agent/run/DEMO-001")
    assert ok.status_code == 200
    run = ok.json()["run_id"]
    assert client.get(f"/agent/runs/{run}").status_code == 200
    assert client.post("/agent/run/T-100").status_code == 401             # real tickets stay private
    seed_user("u_cit")
    assert client.post("/agent/run/T-100", headers=bearer("u_cit")).status_code == 403


def test_local_mode_stays_open_and_admin_token_rules_are_unchanged():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)   # AUTH_REQUIRED=0: the local demo, nothing to sign in to
    assert c.get("/approvals").status_code == 200
    me = c.get("/auth/me").json()
    assert me["role"] == "admin" and me["user_id"] == "local"
    config.ADMIN_TOKEN = "s3cret"
    assert c.post("/citizen/T-1/contact", json={"chat_id": "5"}).status_code == 403
    assert c.post("/citizen/T-1/contact", json={"chat_id": "5"}, headers={"X-Admin-Token": "s3cret"}).status_code == 200


def test_admin_token_still_works_for_scripts_when_auth_is_required(client):
    config.ADMIN_TOKEN = "s3cret"
    r = client.post("/citizen/T-1/contact", json={"chat_id": "5"}, headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 200
    # ...but a decision always needs a person on record
    assert client.post("/approvals/x/decide", json={"decision": "reject"}, headers={"X-Admin-Token": "s3cret"}).status_code == 401
