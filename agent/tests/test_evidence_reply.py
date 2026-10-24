"""Evidence photo uploads (validation, EXIF stripping, idempotency, signed URLs, storage backends) and citizen reply links."""
import io
import json
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app import agent, citizen, config, storage, uploads
from app.db import get_conn
from app.models import now_iso
from app.photo import exif_info
from tests.authkit import bearer, jpeg_bytes, link, png_bytes, seed_user, webp_bytes


@pytest.fixture
def users(client):
    seed_user("u_officer", "officer")
    seed_user("u_linked")
    link("u_linked", "T-100")
    seed_user("u_other")


def up(client, who, data, ticket="T-100", name="a.jpg", ctype="image/jpeg", idem=None):
    h = bearer(who)
    if idem:
        h["Idempotency-Key"] = idem
    return client.post(f"/tickets/{ticket}/evidence/photo", headers=h, files={"file": (name, data, ctype)})


# ---- upload validation ---------------------------------------------------------------------------------------------
def test_valid_photo_is_stored_without_exif_and_gets_no_likelihood_ratio(client, users):
    original = jpeg_bytes(gps=True)
    assert exif_info(Image.open(io.BytesIO(original)))["lat"] == pytest.approx(18.5167, abs=1e-3)   # the input has GPS
    r = up(client, "u_linked", original)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"evidence_id", "sha256", "duplicate"} and body["duplicate"] is False
    assert len(body["sha256"]) == 64
    # the stored copy has no EXIF at all, in particular no GPS
    row = get_conn().execute("SELECT * FROM evidence_uploads WHERE evidence_id=?", (body["evidence_id"],)).fetchone()
    stored = Image.open(Path(config.UPLOAD_DIR) / row["storage_key"])
    assert not stored.getexif() and exif_info(stored) == {"lat": None, "lng": None, "taken_at": None}
    # the original position is kept server-side only and never returned
    assert json.loads(row["exif_summary"])["lat"] == pytest.approx(18.5167, abs=1e-3)
    assert "lat" not in r.text and "exif" not in r.text.lower()
    listed = client.get("/tickets/T-100/evidence", headers=bearer("u_linked")).json()
    assert listed[0]["evidence_id"] == body["evidence_id"] and "exif_summary" not in listed[0]
    # stored for human review: it did not enter the fusion evidence table, so no ratio is applied
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"] == 0
    kinds = [e["event"]["type"] for e in client.get("/audit", headers=bearer("u_officer")).json()]
    assert "evidence_photo_uploaded" in kinds


@pytest.mark.parametrize("data,name,ctype", [(png_bytes(), "a.png", "image/png"), (webp_bytes(), "a.webp", "image/webp")])
def test_png_and_webp_are_accepted(client, users, data, name, ctype):
    assert up(client, "u_linked", data, name=name, ctype=ctype).status_code == 200


@pytest.mark.parametrize("data", [b"just some text, not a picture", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;",
                                  b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"%PDF-1.4 fake", b"RIFFxxxxWAVEfmt "])
def test_wrong_types_are_refused_by_magic_bytes_even_if_the_label_lies(client, users, data):
    r = up(client, "u_linked", data, name="holiday.jpg", ctype="image/jpeg")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media_type"


def test_oversize_empty_and_corrupt_files(client, users):
    config.MAX_UPLOAD_BYTES = 2048
    big = up(client, "u_linked", jpeg_bytes(size=(400, 400), color=(1, 2, 3)) + b"\0" * 4096)
    assert big.status_code == 413 and big.json()["error"]["code"] == "file_too_large"
    config.MAX_UPLOAD_BYTES = 8 * 1024 * 1024
    assert up(client, "u_linked", b"").status_code == 422
    corrupt = up(client, "u_linked", b"\xff\xd8\xff" + b"not really a jpeg" * 20)
    assert corrupt.status_code == 422 and corrupt.json()["error"]["code"] == "unreadable_image"
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence_uploads").fetchone()["n"] == 0


def test_huge_pixel_counts_are_refused(client, users, monkeypatch):
    monkeypatch.setattr(uploads, "_MAX_PIXELS", 100)
    assert up(client, "u_linked", jpeg_bytes(size=(64, 48))).status_code == 422


def test_idempotency_key_and_duplicate_content(client, users):
    data = jpeg_bytes(gps=False)
    first = up(client, "u_linked", data, idem="key-1").json()
    again = up(client, "u_linked", data, idem="key-1").json()
    assert again == first                                              # same key: the stored answer, not a second photo
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence_uploads").fetchone()["n"] == 1
    same_bytes = up(client, "u_linked", data, idem="key-2").json()     # same content, new key
    assert same_bytes["duplicate"] is True and same_bytes["evidence_id"] == first["evidence_id"]
    assert up(client, "u_officer", data, ticket="T-999", idem="key-1").status_code == 200   # keys are per user
    other = client.post("/tickets/T-100/evidence/photo", headers={**bearer("u_officer"), "Idempotency-Key": "k9"},
                        files={"file": ("a.jpg", data, "image/jpeg")})
    assert other.status_code == 200
    moved = client.post("/tickets/T-555/evidence/photo", headers={**bearer("u_officer"), "Idempotency-Key": "k9"},
                        files={"file": ("a.jpg", data, "image/jpeg")})
    assert moved.status_code == 409 and moved.json()["error"]["code"] == "idempotency_conflict"


def test_a_citizen_cannot_attach_to_a_ticket_that_is_not_theirs_and_needs_an_explicit_id(client, users):
    assert up(client, "u_other", jpeg_bytes(), ticket="T-100").status_code == 403
    assert up(client, "u_linked", jpeg_bytes(), ticket="T-200").status_code == 403
    assert client.post("/tickets//evidence/photo", headers=bearer("u_linked"),
                       files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}).status_code in (404, 405)
    assert up(client, "u_linked", jpeg_bytes(), ticket="bad id!").status_code in (404, 422)


# ---- signed urls ---------------------------------------------------------------------------------------------------
def test_signed_url_serves_the_photo_and_rejects_tampering_and_expiry(client, users):
    eid = up(client, "u_linked", jpeg_bytes(gps=False)).json()["evidence_id"]
    got = client.get(f"/evidence/{eid}/url", headers=bearer("u_linked")).json()
    assert got["expires_in"] == config.SIGNED_URL_SECONDS and got["url"].startswith("/evidence/file/")
    img = client.get(got["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(img.content)).size == (64, 48)
    assert client.get(got["url"][:-3] + "abc").status_code == 404                       # tampered signature
    row = get_conn().execute("SELECT storage_key FROM evidence_uploads").fetchone()
    expired = storage.LocalStorage(config.UPLOAD_DIR).signed_url(row["storage_key"], -5)
    assert client.get(expired).status_code == 404
    assert client.get(f"/evidence/{eid}/url", headers=bearer("u_other")).status_code == 403
    assert client.get("/evidence/nope/url", headers=bearer("u_officer")).status_code == 404


def test_local_storage_refuses_paths_outside_its_folder(tmp_path):
    s = storage.LocalStorage(tmp_path / "up")
    with pytest.raises(ValueError):
        s.put("../escape.jpg", b"x", "image/jpeg")


# ---- Supabase storage boundary (mocked HTTP only: not run against a real project) ------------------------------------
def test_supabase_storage_uses_a_private_bucket_and_signed_urls_with_a_mocked_client():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), dict(request.headers), request.content))
        if "/object/sign/" in request.url.path:
            return httpx.Response(200, json={"signedURL": "/object/sign/evidence/T-1/e1.jpg?token=abc"})
        return httpx.Response(200, json={"Key": "evidence/T-1/e1.jpg"})

    s = storage.SupabaseStorage("https://proj.supabase.co/", "service-key", "evidence", httpx.Client(transport=httpx.MockTransport(handler)))
    s.put("T-1/e1.jpg", b"bytes", "image/jpeg")
    url = s.signed_url("T-1/e1.jpg", 300)
    assert url == "https://proj.supabase.co/storage/v1/object/sign/evidence/T-1/e1.jpg?token=abc"
    method, put_url, headers, content = seen[0]
    assert (method, put_url) == ("POST", "https://proj.supabase.co/storage/v1/object/evidence/T-1/e1.jpg")
    assert headers["authorization"] == "Bearer service-key" and headers["content-type"] == "image/jpeg" and content == b"bytes"
    assert json.loads(seen[1][3]) == {"expiresIn": 300}


def test_supabase_backend_without_credentials_is_a_clear_503(client, users):
    config.STORAGE_BACKEND, config.SUPABASE_SERVICE_KEY = "supabase", ""
    try:
        r = up(client, "u_linked", jpeg_bytes())
        assert r.status_code == 503 and r.json()["error"]["code"] == "storage_not_configured"
    finally:
        config.STORAGE_BACKEND = "local"


def test_storage_failure_is_a_503_and_nothing_is_recorded(client, users, monkeypatch):
    class Broken:
        def put(self, *a):
            raise RuntimeError("bucket down")
    monkeypatch.setattr(uploads, "get_storage", lambda: Broken())
    r = up(client, "u_linked", jpeg_bytes())
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence_uploads").fetchone()["n"] == 0


# ---- citizen reply links -------------------------------------------------------------------------------------------
def new_link(client, ticket="T-100", lang="hi"):
    r = client.post("/citizen/reply-links", headers=bearer("u_officer"), json={"ticket_id": ticket, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.mark.parametrize("answer,verdict,lr", [("yes", "supports_fix", citizen.LR_YES), ("no", "contradicts_fix", citizen.LR_NO),
                                               ("partly", "contradicts_fix", citizen.LR_PARTLY)])
def test_reply_goes_through_the_existing_citizen_evidence_path(client, users, answer, verdict, lr):
    token = new_link(client, "T-100", "hi")
    info = client.get(f"/reply/{token}").json()
    assert info == {"ticket_id": "T-100", "category": None, "ward": None, "lang": "hi", "status": "open"}
    r = client.post(f"/reply/{token}", json={"answer": answer})
    assert r.status_code == 200 and set(r.json()) == {"ok", "evidence_id"}
    row = get_conn().execute("SELECT body, run_id FROM evidence WHERE ticket_id='T-100'").fetchone()
    ev = json.loads(row["body"])
    assert (ev["check"], ev["verdict"], ev["likelihood_ratio"]) == ("citizen", verdict, lr) and row["run_id"] is None
    assert client.get(f"/reply/{token}").json()["status"] == "answered"
    events = [e["event"] for e in client.get("/audit", headers=bearer("u_officer")).json()]
    received = [e for e in events if e["type"] == "citizen_reply_received"]
    assert received and received[-1]["channel"] == "reply_link"
    # the answer is fused into a fresh run, like a Telegram reply
    deadline = time.time() + 5
    while time.time() < deadline and not [r_ for r_ in agent.RUNS.values() if r_.ticket_id == "T-100" and r_.status != "running"]:
        time.sleep(0.05)
    run = [r_ for r_ in agent.RUNS.values() if r_.ticket_id == "T-100"][-1]
    assert any("citizen reply on file" in e.summary for e in run.events)


def test_a_link_works_once(client, users):
    token = new_link(client)
    assert client.post(f"/reply/{token}", json={"answer": "yes"}).status_code == 200
    again = client.post(f"/reply/{token}", json={"answer": "no"})
    assert again.status_code == 410 and again.json()["error"]["code"] == "link_used"
    assert get_conn().execute("SELECT COUNT(*) AS n FROM evidence WHERE ticket_id='T-100' AND run_id IS NULL").fetchone()["n"] == 1


def test_an_expired_link_is_refused(client, users):
    from app import reply
    token = reply.make_token("tok-old", "T-100", "en", int(time.time()) - 10)
    get_conn().execute("INSERT INTO reply_links (token_id, ticket_id, lang, expires_at, created_at) VALUES (?,?,?,?,?)",
                       ("tok-old", "T-100", "en", "2020-01-01T00:00:00Z", now_iso()))
    get_conn().commit()
    assert client.get(f"/reply/{token}").json()["status"] == "expired"
    r = client.post(f"/reply/{token}", json={"answer": "yes"})
    assert r.status_code == 410 and r.json()["error"]["code"] == "link_expired"


def test_tampered_or_forged_links_are_plain_404s(client, users):
    from app import reply
    token = new_link(client)
    body, sig = token.split(".")
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    for bad in (flipped + "." + sig, body + "." + sig[:-2] + "xx", token + "x", "garbage", "a.b", body + "."):
        r = client.get(f"/reply/{bad}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "invalid_link", bad
    # a correctly signed token for a link that was never issued has no row
    ghost = reply.make_token("never-issued", "T-100", "en", int(time.time()) + 600)
    assert client.get(f"/reply/{ghost}").status_code == 404
    assert client.post(f"/reply/{ghost}", json={"answer": "yes"}).status_code == 404
    config.REPLY_LINK_SECRET = "a-different-secret-a-different-secret-1"
    assert client.get(f"/reply/{token}").status_code == 404           # signed with another key


def test_reply_answers_must_be_yes_partly_or_no(client, users):
    token = new_link(client)
    assert client.post(f"/reply/{token}", json={"answer": "maybe"}).status_code == 422
    assert client.post(f"/reply/{token}", json={}).status_code == 422
    assert client.get(f"/reply/{token}").json()["status"] == "open"


def test_reply_links_are_rate_limited(client, users):
    codes = [client.get("/reply/not-a-link").status_code for _ in range(32)]
    assert codes[:30] == [404] * 30 and codes[30:] == [429, 429]
    r = client.get("/reply/not-a-link")
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


def test_profile_changes_are_rate_limited(client):
    seed_user("u_new")
    codes = [client.post("/auth/profile", headers=bearer("u_new"), json={"requested_role": "citizen"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_uploads_are_rate_limited(client, users):
    data = jpeg_bytes(gps=False)
    codes = [up(client, "u_officer", data, ticket=f"T-{i}").status_code for i in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
