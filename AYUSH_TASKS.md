# Ayush: Agent service task tracker

Owner: Ayush More. Service: Agent (port 8002). Spec: `backend_ayush.md`. Contract: `00_contract_and_timeline.md`.
Legend: `[x]` done, `[ ]` to do, `(stretch)` only if time allows.

## Phase 0: Setup and contract (10:00-11:00)
- [x] Repo and service skeleton (`agent/`)
- [x] Evidence, Verdict and trace-event fixtures in `contract/`
- [ ] Telegram bot token created
- [ ] WhatsApp Cloud developer app started (approval runs in background)
- [ ] LLM keys tested (Gemini AI Studio, OpenAI), stored in `.env` only

## Phase 1: Core agent with stubs (11:00-13:00)
- [x] Fusion math (log-odds sum)
- [x] Deterministic planner with budget and eligibility guard
- [x] Agent loop with stubbed tools
- [x] SSE trace stream (`GET /agent/stream/{run_id}`)
- [ ] Ishan confirms he sees a live trace from a fake run

## Phase 2: Real inputs, Round A (13:00-16:00)
- [x] Photo verifier v1: imagehash + EXIF
- [x] Approvals table and endpoints
- [x] Audit chain (hash-linked) and `/audit/verify`
- [ ] Photo verifier: add CLIP ViT-B/32 (scene presence, before/after)
- [ ] Call Soham's real Engine score
- [ ] Demo photo set in `data/photos/` with planted failures
- [ ] **Milestone:** agent runs on a real scored ticket

## Phase 3: Citizen channel (16:00-18:00)
- [ ] Telegram round trip: send, reply, parse, Evidence
- [ ] Keyword/number reply parser (en/hi/mr/kn)
- [ ] LLM zero-shot fallback for free-text replies
- [ ] Real satellite tool wired in from Soham
- [ ] **Milestone:** one ticket uses 3 tools

## Phase 4: Closed loop (18:00-20:00)
- [ ] Approve triggers Engine `reopen` / `escalate` (mock municipal endpoint)
- [ ] Outcome check loop (demo mode: 30 s re-run, predicted vs observed)
- [ ] Audit `/audit/verify` passes after a full run
- [ ] **Milestone:** closed loop works

## Phase 5: LLM planner and WhatsApp, Round B (20:00-22:00)
- [ ] `llm.py` provider chain: Gemini, OpenAI, deterministic fallback
- [ ] LLM-chosen tool calls with schema validation, one retry, then fallback
- [ ] Guardrail tests (ineligible tool, budget, `propose_action` only path, hashed IDs)
- [ ] Fallback tested with network off
- [ ] WhatsApp Cloud round trip (only after Telegram passes)
- [ ] **Milestone:** full demo

## Phase 6: Calibration and polish (22:00-02:00)
- [ ] Calibrate likelihood ratios on `data/benchmark_v1.parquet`
- [ ] Cost-vs-accuracy experiment (agent vs run-everything)
- [ ] Dockerfile / docker-compose, deploy
- [ ] (stretch) DINOv2-small second embedding
- [ ] (stretch) Skeptic call on final verdict
- [ ] (stretch) Whisper voice notes via hosted API

## Phase 7: Freeze (07:00-09:00)
- [ ] Offline-mode rehearsal
- [ ] Interface checklist passes (see `backend_ayush.md` section 12)
- [ ] Code freeze

## Working rules
- All commits are authored by Ayush More only. No co-author trailers.
- Secrets live in `.env`, never in git.
