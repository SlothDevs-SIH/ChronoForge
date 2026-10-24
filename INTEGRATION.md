# Integration report: Engine (Soham) + Agent (Ayush)

Status on 24 Oct. Branch `integration` (local until pushed). Nothing here is deployed.

## What was merged
`soham-backend` (Phases 1 to 4) and Ayush's branch (**`ayush`**, 11 commits; `ayush-backend` is empty). The only conflicts were in the scaffold agent files I had patched (`agent/app/main.py`, `planner.py`, `tools.py`, `tests/test_agent.py`); his real Agent replaces the scaffold. Everything else merged cleanly.

## Ayush's branch on its own
- **96 of 96 tests pass** in an isolated environment. No secrets in tracked files (his `.env.example` values are empty).
- Architecture is sound: a code-level guard on every planner choice, a rule that a score alone never gives a verdict, a skeptic pass, SQLite persistence, a hash-chained audit, approvals that only create a pending row.
- **Not re-verified by me** (need his tokens or large downloads): the live Telegram round trip and the Gemini planner (he reports both verified live), WhatsApp (he reports it parked on Meta's "claim test number" error), and the CLIP and DINOv2 models (not downloaded).

## Verified live: Engine on the full warehouse plus his Agent with `AGENT_USE_STUBS=0`
| Scenario | Result |
|---|---|
| Planted failure: reused photo (DEMO-003, 004) | caught, posterior 0.97, reopen proposed |
| Planted failure: shifted GPS (005) / stale timestamp (007) | caught, posterior 0.80 / 0.75 |
| Clean demo tickets (000, 001, g00) | no false accusation: `cannot_tell` at 0.33 |
| Planted failure: **still broken** (DEMO-009) | **missed**: "supports fix" (see risk 2) |
| Real Mumbai ticket with a cached satellite result | satellite evidence enters the trace (LR 1.25, posterior 0.56) |
| Real Bengaluru ticket, highest risk (prior 0.70) | no evidence available: `cannot_tell` |
| Unknown ticket id | run fails loudly ("cannot get a score from the Engine"), no invented prior |
| Approve a reopen | Engine marks it `reopened`, ward stats update, audit chain verifies (125 entries) |
| His `experiments/rehearsal.py` against the live Engine | passes (20 real tickets, audit verifies) |

Tests after integration: engine 166, agent 105 (his 96 plus 9 for the integration), web type-check clean.

## Fixed during integration
1. **Satellite timeout.** His `_engine` helper hard-codes 5 s; a live Sentinel-2 read takes 20 to 60 s, so every live call would have failed as "engine unreachable". The tool now asks for the cached answer first (instant), then a live read with `SATELLITE_TIMEOUT` (120 s), and abstains with an honest reason on failure.
2. **Silent stub fallback.** With real services on, an unreachable Engine or an unknown ticket silently got an invented stub prior. It now raises (`AGENT_ALLOW_STUB_FALLBACK=1` restores the old behaviour).
3. **Demo tickets were invisible to the Engine.** His `DEMO-*` photo set had no tickets in the warehouse, so the real photo verifier had nothing to check. New `demo` source loads his manifest as 12 synthetic tickets (planted failures kept in a separate truth file; photo paths repo-relative).
4. **Frontend would have shown an empty trace.** His SSE sends named `trace` events and the web client only listened for unnamed ones. The client now handles both.

## Risks and findings, most important first
1. **On real tickets the agent has almost no evidence.** Real tickets have no closure photo, no citizen contact, and only 0.7% qualify for a satellite check, so ordinary real tickets end `cannot_tell` at their prior (20 of 20 in the rehearsal). The closed loop is demonstrable only on the demo set, on tickets with a registered Telegram contact, and on the few satellite-eligible tickets. The pitch must not imply otherwise.
2. **CLIP is off by default, so "still broken" photos pass.** The photo checks without CLIP are duplicate, GPS and timestamp only; a closure photo that still shows the pothole is called "supports fix". Turning CLIP on needs torch (about 2 GB) and a 400 MB model, and his tracker says it has not been run with the real model. Until then do not present photo content checks.
3. **Likelihood ratios are hand-set** (duplicate 8, far GPS 4, stale 3, clean 0.5). His tracker plans to calibrate them on `benchmark_v1`. That would be circular: the benchmark's symptom rates are numbers we chose, so a "calibrated" ratio would just echo them. Recommend stating them as hand-set assumptions.
4. **Outcome check is weak.** After an approved reopen it re-runs the agent and compares verdicts, but with the same evidence the verdict cannot change. It demonstrates the mechanism; real outcome verification needs a new satellite pass or a citizen reply after the reopen.
5. **Cost versus accuracy.** His harness runs on stub ground truth. The benchmark has no per-tool outputs for the citizen or satellite checks, so any real number would be a simulation with invented tool behaviour. Needs a decision (see below).
6. **Order matters for duplicates.** A reused photo is only caught if the original was checked first (the first holder is clean by definition). The demo must run the originals first.
7. **The Telegram path is demo-only:** a ticket needs a registered chat (`POST /citizen/{id}/contact`) before the agent can ask anyone.

## Decisions needed
- Cost versus accuracy: run a labelled simulation, or leave it as "pending" in the pitch?
- CLIP: install and verify it before the demo, or drop photo content checks from the claims?
- Photos for real tickets: none exist. Keep the demo set as the only photo path, or add a few real Mumbai tickets to the demo with planted photos?

## Run it integrated
```bash
cd engine && python -m app.ingest all        # includes the demo set
cd engine && uvicorn app.main:app --port 8001
cd agent  && AGENT_USE_STUBS=0 uvicorn app.main:app --port 8002     # his dependencies: pip install -r agent/requirements.txt
cd web && npm run dev
```
Use separate virtual environments for `engine/` and `agent/` (both packages are named `app`; I tested them separately). Useful agent settings: `ENGINE_URL`, `SATELLITE_TIMEOUT`, `STEP_DELAY`, `AGENT_USE_LLM_PLANNER`, `AGENT_USE_CLIP`, `LLM_PROVIDERS`. Keys live in `agent/.env`, never in git.
