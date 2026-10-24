# Ayush: Agent service task tracker

Owner: Ayush More. Service: Agent (port 8002). Spec: `backend_ayush.md`. Contract: `00_contract_and_timeline.md`.
Legend: `[x]` done, `[ ]` to do, `(stretch)` only if time allows.

## Phase 0: Setup and contract
- [x] Repo and service skeleton (`agent/`)
- [x] Evidence, Verdict and trace-event fixtures in `contract/`
- [x] Telegram bot token created (@TruClosebot)
- [ ] WhatsApp Cloud developer app started (approval runs in background)
- [ ] LLM keys tested: Gemini done and working live; OpenAI not added

## Phase 1: Core agent with stubs
- [x] Fusion math (log-odds sum)
- [x] Deterministic planner with budget and eligibility guard
- [x] Agent loop with stubbed tools
- [x] SSE trace stream (`GET /agent/stream/{run_id}`)
- [ ] Ishan confirms he sees a live trace from a fake run

## Phase 2: Real inputs, Round A
- [x] Photo verifier v1: imagehash + EXIF
- [x] Approvals table and endpoints
- [x] Audit chain (hash-linked) and `/audit/verify`
- [x] Photo verifier: add CLIP ViT-B/32 (scene presence, before/after) (code + tests done; real model run still to try)
- [ ] Call Soham's real Engine score
- [x] Demo photo set with planted failures (synthetic placeholders via `experiments/make_demo_photos.py`; swap in real photos)
- [ ] **Milestone:** agent runs on a real scored ticket

## Phase 3: Citizen channel
- [x] Telegram round trip: send, reply, parse, Evidence (verified live with @TruClosebot, long-polling)
- [x] Keyword/number reply parser (en/hi/mr/kn)
- [x] LLM zero-shot fallback for free-text replies
- [ ] Real satellite tool wired in from Soham
- [ ] **Milestone:** one ticket uses 3 tools

## Phase 4: Closed loop
- [x] Approve triggers Engine `reopen` / `escalate` (code + tests; live check needs Soham's Engine)
- [x] Outcome check loop (demo mode: 30 s re-run, predicted vs observed)
- [x] Audit `/audit/verify` passes after a full run
- [ ] **Milestone:** closed loop works

## Phase 5: LLM planner and WhatsApp, Round B
- [x] `llm.py` provider chain: Gemini, OpenAI, deterministic fallback
- [x] LLM-chosen tool calls with schema validation, one retry, then fallback
- [x] Guardrail tests (ineligible tool, budget, `propose_action` only path, hashed IDs)
- [x] Fallback tested with network off (simulated in tests)
- [ ] WhatsApp Cloud round trip (code + tests done; needs Meta credentials)
- [ ] **Milestone:** full demo

## Phase 6: Calibration and polish
- [ ] Calibrate likelihood ratios on `data/benchmark_v1.parquet`
- [ ] Cost-vs-accuracy experiment (harness done on stub data; needs real benchmark numbers)
- [ ] Dockerfile / docker-compose (written, not built: no Docker here); deploy still to do
- [ ] (stretch) DINOv2-small second embedding
- [ ] (stretch) Skeptic call on final verdict
- [ ] (stretch) Whisper voice notes via hosted API

## Phase 7: Freeze
- [ ] Offline-mode rehearsal
- [ ] Interface checklist passes (see `backend_ayush.md` section 12)
- [ ] Code freeze

## Working rules
- All commits are authored by Ayush More only. No co-author trailers.
- Secrets live in `.env`, never in git.
