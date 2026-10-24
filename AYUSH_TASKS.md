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
- [x] Call Soham's real Engine score (verified live against his Engine, fixtures mode)
- [x] Demo photo set: real open-licence Commons photos + planted failures (demo/photos, ATTRIBUTION.md); synthetic only for streetlight/drain and EXIF
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
- [ ] WhatsApp Cloud round trip (code + tests done; PARKED: Meta "Claim test number" fails with a generic error; retry later)
- [ ] **Milestone:** full demo

## Phase 6: Calibration and polish
- [ ] Calibrate likelihood ratios: NOT meaningful yet. Soham's benchmark is synthetic injection (caught by construction), so hand-set LRs stay and are labelled as such
- [x] Cost-vs-accuracy harness on real tools over the 12-ticket demo set (illustration, not a result): experiments/cost_demo_set.py
- [x] Dockerfile builds from repo root (written, not built: no Docker here); deploy deliberately not done yet
- [x] (stretch) DINOv2-small second embedding (code + tests; real model not downloaded yet)
- [x] (stretch) Skeptic call on final verdict (AGENT_USE_SKEPTIC=1)
- [x] (stretch) Voice notes via hosted API (Gemini audio, not Whisper; code + tests)

## Phase 7: Freeze
- [x] Offline-mode rehearsal (experiments/rehearsal.py passes against the Engine; re-run after Soham's warehouse lands)
- [x] Interface checklist passes (tests/test_interface.py; benchmark path item waits on Soham)
- [ ] Code freeze

## Working rules
- All commits are authored by Ayush More only. No co-author trailers.
- Secrets live in `.env`, never in git.
