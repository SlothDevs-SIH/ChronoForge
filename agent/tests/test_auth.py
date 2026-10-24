from fastapi.testclient import TestClient

from app import auth, config
from app.main import app

client = TestClient(app)


def _signup(email, role="citizen"):
    config.AUTH_ENFORCE = True
    r = client.post("/auth/register", json={"email": email, "name": "T", "password": "longenough1", "role": role})
    assert r.status_code == 200, r.text
    return client.post("/auth/login", json={"email": email, "password": "longenough1"}).json()["token"]


def h(t):
    return {"Authorization": f"Bearer {t}"}


def test_officer_endpoints_need_sign_in_and_the_right_role():
    citizen = _signup("c@x.in")
    assert client.get("/approvals").status_code == 401
    assert client.get("/approvals", headers=h(citizen)).status_code == 403
    officer = _signup("o@x.in", "officer")
    assert client.get("/approvals", headers=h(officer)).status_code == 403   # pending grants nothing


def test_admin_approves_officer_then_officer_gets_in():
    config.FIRST_ADMIN_EMAIL, config.FIRST_ADMIN_PASSWORD = "a@x.in", "adminpass123"
    auth.seed_admin()
    admin = client.post("/auth/login", json={"email": "a@x.in", "password": "adminpass123"}).json()["token"]
    officer = _signup("o@x.in", "officer")
    uid = [u for u in client.get("/admin/users", headers=h(admin)).json() if u["email"] == "o@x.in"][0]["user_id"]
    assert client.post(f"/admin/users/{uid}/status", json={"status": "active"}, headers=h(admin)).status_code == 200
    assert client.get("/approvals", headers=h(officer)).status_code == 200
    assert client.get("/admin/users", headers=h(officer)).status_code == 403


def test_cannot_self_register_as_admin_and_bad_password_fails():
    r = client.post("/auth/register", json={"email": "z@x.in", "name": "Z", "password": "longenough1", "role": "admin"})
    assert r.status_code == 400
    _signup("c@x.in")
    assert client.post("/auth/login", json={"email": "c@x.in", "password": "wrong"}).status_code == 401


def test_tampered_token_is_rejected():
    t = _signup("c@x.in")
    assert client.get("/auth/me", headers=h(t[:-2] + "00")).status_code == 401


def test_citizen_keeps_their_own_ticket_list():
    t = _signup("c@x.in")
    assert client.post("/me/tickets", json={"ticket_id": "T-1"}, headers=h(t)).json() == ["T-1"]
