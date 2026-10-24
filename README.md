# TrueClose (ChronoForge, Team Slothdevs)

**TrueClose verifies that closed civic complaints are actually fixed.** An agent scores each ticket marked "resolved", picks the cheapest independent check (photo, satellite, citizen, human), fuses the evidence, and proposes a reopen that a human must approve.

Start with `PROJECT_OVERVIEW.md`, then `INTEGRATION.md` (how the Engine and Agent fit together, what is verified, what is risky), then `contract/README.md`; Soham's workflow is in `soham.md`. Per-person plans: `backend_soham.md` (Engine), `backend_ayush.md` (Agent), `frontend_ishan.md` (web), `research_vedashri.md`.

## Layout
```
contract/   JSON fixtures that define the data contract (also used as service fixtures)
engine/     Engine service, FastAPI, port 8001   (Soham)
agent/      Agent service, FastAPI, port 8002    (Ayush)
web/        React + Vite + TypeScript            (Ishan)
```

## Run it (three terminals, from the repo root)
```bash
# Engine (its own virtual environment: both services use a package named `app`)
pip install -r engine/requirements.txt
cd engine && python -m app.ingest all                 # needs data/raw (see data/README.md); without it the Engine serves 6 fixtures
cd engine && uvicorn app.main:app --port 8001

# Agent (Ayush's service; its own virtual environment)
pip install -r agent/requirements.txt
cd agent && AGENT_USE_STUBS=0 uvicorn app.main:app --port 8002     # 1 = stub tools, no Engine needed

cd web && npm install && npm run dev                  # http://localhost:5173
```
API docs: http://localhost:8001/docs and http://localhost:8002/docs. Tests: `cd engine && pytest`, `cd agent && pytest` (run separately, both packages are named `app`).

## What is real and what is not (after integration)
| Piece | State |
|---|---|
| Connectors, warehouse (about 822,800 real and synthetic tickets), scorer, satellite verifier, benchmark | Real, with the limits in `data/README.md` and `data/models/*.metrics.json` |
| Agent: fusion, guarded planner, approvals, audit, SQLite, skeptic | Real, tested (Ayush) |
| Photo verifier (duplicate, GPS, timestamp) | Real; **CLIP and DINOv2 are off by default and not run with the real models** |
| LLM planner and reply classifier (Gemini, OpenAI) | Real code; live runs need keys; the deterministic planner is the fallback |
| Telegram | Real code, live-verified by Ayush; WhatsApp parked on a Meta error |
| Web app (React, Vite): landing, how it works, platform, evaluation, overview with ward map, triage, ticket detail, approvals, audit log | Real, built on the live Engine and Agent APIs; the ward map is a plain SVG dot map (no basemap tiles); the citizen web page is **not built** |
| Municipal system | **Simulated** (reopen and escalate flip a status in the Engine) |
| Photos | Only the 12-ticket `demo` set; real tickets have none |
| Agent with stubs on (`AGENT_USE_STUBS=1`) | Stub tools: plumbing only, never a result |

On ordinary real tickets the agent has almost no evidence (see `INTEGRATION.md`). Never present stub output as a result.

## Prior work
GEOAI-04 (satellite change engine) and the Catalyst AI engines are our earlier projects and are reused here as acknowledged prior components. The closure-integrity logic, agent, connectors and verification loop are new this weekend.
