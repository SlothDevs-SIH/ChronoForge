# Agent service (port 8002) — Ayush

Built so far (see `../backend_ayush.md`): fusion math, deterministic planner + guard, agent loop with SSE trace,
approvals + outcome check, hash-chained audit log, photo verifier v1 (imagehash + EXIF).
Tools default to deterministic **stubs** (`AGENT_USE_STUBS=1`, labelled `stub` in the trace) until the Engine,
Telegram and CLIP are wired. Optional: `AGENT_USE_CLIP=1` (install `requirements-clip.txt`), `AGENT_USE_LLM_PLANNER=1` (needs a Gemini or OpenAI key).
Telegram: `POST /citizen/{ticket}/contact` links a demo chat, webhook is `POST /channels/telegram/webhook`. Not built yet: WhatsApp, LR calibration.

    py -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/python -m uvicorn app.main:app --port 8002
    .venv/Scripts/python -m pytest

Endpoints: `POST /agent/run/{id}`, `GET /agent/stream/{run_id}` (SSE), `GET /agent/runs/{run_id}`,
`POST /evidence/photo`, `GET /approvals`, `POST /approvals/{id}/decide`, `GET /outcomes`, `GET /audit`, `GET /audit/verify`.
Schema: `sql/schema.sql`. Thresholds, budget, costs: `app/config.py`.
