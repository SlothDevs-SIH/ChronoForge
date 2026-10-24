import json

import httpx
from fastapi.testclient import TestClient

from app import agent, audit, config, llm, telegram, whatsapp
from app.main import app
from experiments import cost_vs_accuracy, make_demo_photos


def wa_payload(wa_id, text, kind="text"):
    msg = {"from": wa_id, "type": kind}
    msg["text" if kind == "text" else "image"] = {"body": text} if kind == "text" else {"caption": text}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def test_parse_whatsapp_payload():
    assert whatsapp.parse_payload(wa_payload("9190", "2")) == [{"wa_id": "9190", "text": "2", "has_photo": False}]
    assert whatsapp.parse_payload(wa_payload("9190", "still broken", "image"))[0]["has_photo"] is True
    assert whatsapp.parse_payload({"entry": [{"changes": [{"value": {"statuses": []}}]}]}) == []


def test_whatsapp_round_trip_and_channel_isolation(monkeypatch):
    monkeypatch.setattr(agent, "run_in_background", lambda run_id: None)
    client = TestClient(app)
    telegram.register_contact("t1", "9190", "mr", channel="whatsapp")
    sent = []
    telegram.send_request("t1", "pothole", "x", "y", sender=lambda c, t: sent.append(c))
    # same id on telegram must not match the whatsapp request
    assert telegram.handle_reply("telegram", "9190", "2") is None
    r = client.post("/channels/whatsapp/webhook", json=wa_payload("9190", "2"))
    assert r.status_code == 200 and len(r.json()["run_ids"]) == 1
    assert "9190" not in str(audit.entries(200))


def test_whatsapp_verify_handshake(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(config, "WHATSAPP_VERIFY_TOKEN", "vt")
    ok = client.get("/channels/whatsapp/webhook",
                    params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    bad = client.get("/channels/whatsapp/webhook",
                     params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "123"})
    assert bad.status_code == 403


def test_agent_completes_with_network_off(monkeypatch):
    """Venue Wi-Fi down: LLM calls raise, the LLM planner falls back, the run still reaches a verdict."""
    def no_network(*a, **kw):
        raise httpx.ConnectError("network is off")
    monkeypatch.setattr(httpx, "post", no_network)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "USE_LLM_PLANNER", True)
    assert llm.available_providers() == ["gemini", "openai"]
    run_id = agent.start_run("T-offline")
    v = agent.execute(run_id, delay=0)
    run = agent.RUNS[run_id]
    assert v.state in ("verified_fixed", "likely_not_fixed", "cannot_tell")
    assert any("fallback: deterministic planner" in e.summary for e in run.events)
    assert audit.verify()["ok"]


def test_cost_vs_accuracy_harness_runs(capsys):
    cost_vs_accuracy.main(20)
    out = capsys.readouterr().out
    assert "STUB DATA" in out and "adaptive agent" in out and "run everything" in out


def test_demo_photo_set_has_labelled_planted_failures(tmp_path):
    make_demo_photos.main(str(tmp_path), 24)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest) == 24 and all(m["data_quality"] == "synthetic" for m in manifest)
    assert {m["plan"] for m in manifest} == {"clean", "reused", "shifted_gps", "stale_time", "still_broken"}
    from app import photo
    idx = photo.PhotoIndex(str(tmp_path / "idx.json"))
    results = {}
    for m in manifest:                        # first pass indexes every photo, second pass checks it
        idx.add(m["ticket_id"], photo.hashes(photo.load_image(str(tmp_path / m["after"]))))
    for m in manifest:
        ev = photo.verify_photo(m["ticket_id"], str(tmp_path / m["after"]), m, idx, use_clip=False)
        results[m["plan"]] = results.get(m["plan"], []) + [ev.verdict]
    assert all(v == "contradicts_fix" for v in results["reused"])
    assert all(v == "contradicts_fix" for v in results["shifted_gps"])
    assert all(v == "contradicts_fix" for v in results["stale_time"])


def test_whatsapp_send_text_and_template_shape(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_TOKEN", "tok")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "123")
    sent = []

    class R:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "post", lambda url, **kw: sent.append((url, kw)) or R())
    whatsapp.send_text("9190", "hi")
    whatsapp.send_template("9190")
    assert sent[0][0].endswith("/123/messages") and sent[0][1]["json"]["type"] == "text"
    assert sent[1][1]["json"]["template"]["name"] == "hello_world"
    assert sent[0][1]["headers"]["Authorization"] == "Bearer tok"
