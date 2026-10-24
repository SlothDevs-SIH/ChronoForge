# TrueClose (ChronoForge, Team Slothdevs)

**TrueClose verifies that closed civic complaints are actually fixed.** An agent scores each ticket marked "resolved", picks the cheapest independent check (photo, satellite, citizen, human), fuses the evidence, and proposes a reopen that a human must approve.

Start with `PROJECT_OVERVIEW.md`, then `contract/README.md`; Soham's workflow is in `soham.md`. Per-person plans: `backend_soham.md` (Engine), `backend_ayush.md` (Agent), `frontend_ishan.md` (web), `research_vedashri.md`.

## Layout
```
contract/   JSON fixtures that define the data contract (also used as service fixtures)
engine/     Engine service, FastAPI, port 8001   (Soham)
agent/      Agent service, FastAPI, port 8002    (Ayush)
web/        React + Vite + TypeScript            (Ishan)
```

## Run it (three terminals, from the repo root)
```bash
python -m venv .venv && .venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r engine/requirements.txt -r agent/requirements.txt

cd engine && uvicorn app.main:app --port 8001 --reload
cd agent  && uvicorn app.main:app --port 8002 --reload
cd web && npm install && npm run dev                  # http://localhost:5173
```
API docs: http://localhost:8001/docs and http://localhost:8002/docs. Tests: `cd engine && pytest`, `cd agent && pytest` (run separately, both packages are named `app`).

## What is real and what is a stub (skeleton stage)
| Piece | State |
|---|---|
| Contract fixtures, endpoint shapes, CORS, dev proxy | Real |
| Evidence fusion (log-odds), verdict thresholds, budgeted planner loop, SSE trace | Real, tested |
| Approval gate, simulated municipal reopen, outcome check, hash-chained audit log | Real, tested |
| Scorer, connectors, satellite verifier, ward stats, eval results | **Stub**: served from `contract/*.json` (`eval_results.json` is marked `is_placeholder`) |
| Photo verifier, citizen channel (Telegram/WhatsApp), LLM chooser | **Stub** (`details.stub = true`) |

Everything in the stub rows is replaced during the hackathon. Never present stub output as a result.

## Prior work
GEOAI-04 (satellite change engine) and the Catalyst AI engines are our earlier projects and are reused here as acknowledged prior components. The closure-integrity logic, agent, connectors and verification loop are new this weekend.
