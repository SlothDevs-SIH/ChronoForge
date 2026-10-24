# Backend B: Agent service (Ayush)

Port 8002. Python 3.11, FastAPI. Read `contract/README.md` first.
Decision points marked **[Qn]** are in `questions.md`. Where I state a lean, it is a recommendation and not a lock.

## 1. What this service is

The Agent service is the brain and the hands. It calls Soham's Engine for scores and satellite evidence, adds its own evidence (photo forensics, citizen replies), decides which check to run next under a budget, fuses everything into a verdict, and routes any action through human approval with an audit trail.

Five modules, in build order:

1. Evidence store and photo verifier
2. Agent planner and fusion (the core)
3. Citizen channel (Telegram first, WhatsApp second)
4. Approvals and actions
5. Audit log

## 2. Why this is "agentic" and not a pipeline (judges will ask)

| Criterion | Where it lives |
|---|---|
| Autonomy | Given a ticket id, the agent runs without further input until it reaches a verdict or runs out of budget |
| Tool use | Six typed tools (below), chosen at runtime |
| Decision under uncertainty | Picks the next check by expected information gain per unit cost; abstains when evidence stays ambiguous |
| Outcome verification | After an approved reopen, the agent schedules a follow-up check and compares predicted vs observed result |
| Safety | Human approval gate, no auto-penalty, every step logged |

## 3. Module 1: Evidence store and photo verifier

### What
Checks whether the **closure proof** is credible. The closing officer supplies the photo, so it is the weakest link in today's systems.

### Checks
| Check | Method | Signal |
|---|---|---|
| Reused photo | Perceptual hash (pHash/dHash via `imagehash`) plus embedding cosine similarity against all prior closure photos | Same or near-same image appears on another ticket: strong evidence of a false closure |
| Location consistency | EXIF GPS vs ticket lat/lng; EXIF timestamp vs `closed_at` | Photo taken far away or long before the claimed fix |
| Scene presence | Zero-shot CLIP: similarity to "a pothole on a road" vs "a smooth road" (category-specific prompts) | Closure photo still shows the problem |
| Before/after match | Embedding similarity between the complaint photo and the closure photo | Same place or a different place |
| Photo-of-a-photo (stretch) | Frequency-domain moire / screen-glare cues | Re-photographed screen |

### Options **[Q8]**
| Option | Model | Pros | Cons |
|---|---|---|---|
| A. imagehash + EXIF only | No ML | Instant, explainable, runs anywhere | Misses crops and edits |
| B. A + CLIP (ViT-B/32 via `open_clip`, ONNX or PyTorch CPU) | Embeddings and zero-shot | Robust to crops and brightness; also gives scene presence | 400 MB download, CPU slowish |
| C. B + DINOv2-small | Better instance-level matching | Best duplicate detection | More weight, more setup |
| D. Vision LLM judge (Claude, Gemini) on image pairs | API call | No training, flexible reasoning | Cost, latency, hard to calibrate, privacy |

**DECIDED (Q8): B.** `imagehash` + EXIF + CLIP ViT-B/32 (CPU). In plain terms: imagehash and EXIF are the quick checks (exact copies, wrong place or time), and CLIP adds robustness to crops/edits and the "does it still show a pothole" test. **Stretch (only if time after Round B): add DINOv2-small** for stronger same-scene matching. It plugs into the same `check_photo` function as a second embedding, so the agent and the contract do not change. Optional: a Gemini vision call as a second opinion, labelled as such. The proposal says ONNX Runtime with DINOv2 or CLIP, so B stays consistent with the slides.

### Index
Store embeddings in a NumPy matrix on disk and use brute-force cosine similarity. At a few thousand photos this takes milliseconds, so FAISS is unnecessary. Add FAISS only if the photo count exceeds about 100k.

### Output
Evidence contract, `check = "photo"`. Map to a likelihood ratio: exact or near-duplicate gives LR about 8, EXIF location far away gives LR about 4, scene still shows the problem gives LR about 5, clean passes give LR about 0.5. Initial values are hand-set. Soham's benchmark (shared parquet) is used to calibrate them in the later hours.

### Demo photos
Real closure photos are not in the BBMP data. Build a small set (`data/photos/`, 60-100 images): public pothole and garbage images (Kaggle pothole datasets, Mapillary, our own phone photos around campus, all from licence-clean sources), each ticket assigned a "before" and "after", and deliberately planted failures (a reused image, a shifted location, a still-broken after photo). Label them as demo data.

## 4. Module 2: Agent planner and fusion (the heart of the project)

### State
Per run: `ticket`, `prior` (Engine score), `evidence[]`, `posterior`, `budget_left`, `trace[]`.

### Tools the agent can call
| Tool | Cost | Calls | Returns |
|---|---|---|---|
| `get_score(ticket_id)` | 0 | Engine | Score |
| `check_photo(ticket_id)` | 1 | Module 1 | Evidence |
| `check_satellite(ticket_id)` | 3 | Engine | Evidence (cost 0 and inconclusive if ineligible) |
| `ask_citizen(ticket_id)` | 2 | Module 3 | Evidence arrives later (asynchronous) |
| `request_human_spot_check(ticket_id)` | 10 | Approvals queue | Evidence from human |
| `propose_action(ticket_id, action)` | 0 | Module 4 | Creates an approval item, never acts alone |

### Decision loop
```
1. posterior <- prior
2. while budget_left > 0 and posterior in uncertain band (0.25, 0.75):
3.     candidates <- tools whose eligibility passes (e.g. satellite only if satellite_eligible)
4.     pick tool maximising  expected_info_gain(tool, posterior) / cost(tool)
5.     result <- call tool;  posterior <- fuse(posterior, result.likelihood_ratio)
6.     emit trace event
7. verdict <- threshold(posterior)  (fixed / not fixed / cannot_tell)
8. if verdict == not fixed: propose_action(reopen) -> human approval
9. after outcome: record predicted vs observed -> outcome-verification table
```
- **Fusion**: log-odds sum (see contract). It assumes independence between checks, which is approximate. State this assumption in the deck instead of hiding it. A small improvement is to down-weight correlated pairs (photo and citizen) by 0.7.
- **Expected information gain**: for each tool, use the tool's historical LR distribution from the benchmark to compute the expected reduction in posterior entropy. A simpler **heuristic version** is acceptable for 24 h: a fixed ordered preference table by category (cheap first, satellite only when eligible and the posterior is still uncertain), with the information gain formula as a stretch.
- **Abstention**: if the budget runs out and the posterior is still in 0.25-0.75, the verdict is `cannot_tell` and the recommended action is `human_spot_check`. Abstentions are counted and shown.

### Where the LLM goes **[Q9]**
| Option | Role of the LLM | Pros | Cons |
|---|---|---|---|
| A. Deterministic planner, LLM writes explanations only | LLM turns the trace into a plain-language reason | Reproducible, cheap, safe, easy to evaluate | Judges may say "that's just rules" |
| B. LLM chooses the next tool with strict JSON tool calling, deterministic planner as fallback and as a guard | The LLM plans; code validates and enforces budget and eligibility | Really agentic, demonstrable reasoning, graceful fallback | Nondeterministic; needs retries and a schema |
| C. Framework (LangGraph, CrewAI, OpenAI Agents SDK) | Same as B inside a framework | Visual graph, conventions | Heavy dependency, slower debugging, more magic |
| D. Multi-agent (Investigator, Skeptic, Judge) | Three LLM roles debate | Great story | Cost, latency, hard to keep deterministic |

**DECIDED (Q9): B, the LLM chooses the next tool.** Hand-written loop, no framework (about 150 lines, fully debuggable). Code enforces eligibility and budget and falls back to the deterministic planner. Optional after Round B: one "skeptic" call on the final verdict (argues why the closure might be real; the verdict stands only if the skeptic finds no hole).

### LLM provider **[Q10]** (decided: use what we have)
We hold keys for several providers. Put them behind one thin `llm.py` interface (`complete_json(prompt, schema) -> dict`) with a provider list in `.env`, tried in order, then the deterministic planner:
1. **Gemini via the Google AI Studio API key** as primary (free tier has rate limits; the Gemini Pro app subscription is separate from API access, so test the key in the first hour).
2. **OpenAI API** (the large token allowance) as the second provider.
3. **Deterministic planner** as the last fallback.
Rules: keys live only in `.env`, never in git. Log which provider answered each step (shown in the trace). **Test the fallback by unplugging the network**, because venue Wi-Fi is the most likely thing to break. A model can be swapped per call, for example a fast model for intent parsing and a stronger one for planning.

### Guardrails (write these as tests)
- Output must validate against a Pydantic schema; invalid output triggers one retry, then the fallback.
- The LLM cannot call a tool that is ineligible or exceeds the budget; the code rejects it.
- `propose_action` is the only way to request a reopen, and it always creates an approval item.
- The LLM never sees raw phone numbers or officer identifiers, only hashes.

### Trace streaming
Every step is appended to the run and pushed as an SSE event (`GET /agent/stream/{run_id}`) in the Agent trace event format. This is what Ishan renders as the live "agent thinking" panel, and it is the most persuasive 20 seconds of the demo.

## 5. Module 3: Citizen channel (MVP component)

### What
Send the original complainant a short "Was it fixed?" message in their language and parse the reply into Evidence.

### Flow
```
ask_citizen(ticket_id)
  -> message in lang (en/hi/mr/kn): "Your complaint about <category> near <area> was marked fixed on <date>. Was it fixed? Reply 1 Yes, 2 No, 3 Partly, or send a photo."
  -> webhook receives reply (text, number, voice note, photo)
  -> parse intent -> Evidence {check: citizen, verdict, LR}
  -> if photo: also run Module 1 on it
```
LR guide: a clear "No" from the real complainant gives LR about 6; "Yes" gives about 0.3; "Partly" gives about 2; no reply after 48 h gives about 1.2 (silence is weak evidence, never a sign of satisfaction; that is the point of the project).

### Channel options **[Q11]**
| Option | Effort | Reliability | Notes |
|---|---|---|---|
| A. Telegram bot (`python-telegram-bot` or aiogram, webhook via ngrok/Cloudflare tunnel) | 1-2 h | High | No business verification; instant; demoable on any phone |
| B. WhatsApp Cloud API (Meta) | 3-5 h plus verification risk | Medium | Free test number can message only pre-registered recipients (up to 5); templates need approval for out-of-window messages; test credentials are free but the tokens expire |
| C. Twilio WhatsApp sandbox | 1-2 h | Medium | Sandbox join code required for each user; paid beyond trial |
| D. SMS (Twilio, Fast2SMS) | 1-2 h | Medium | DLT registration issues in India; costs |
| E. Web link only ("Was it fixed?" mobile page) | 1 h | High | Safe fallback; Ishan builds it anyway |

**DECIDED (Q11): Telegram first; once Telegram is fully working, WhatsApp Cloud API.** The web link (E) is built by Ishan anyway as a fallback. The proposal names WhatsApp, so a WhatsApp round trip with 2-3 team phones registered as test recipients should work before the final. Do not start WhatsApp until the Telegram round trip (send, reply, parse, Evidence) passes its test. Start Meta developer app setup in hour one in the background, because approvals can take time.

### Language understanding **[Q12]**
| Option | Pros | Cons |
|---|---|---|
| A. Regex and keyword map (1/2/3, "yes/no/ho/nahi/हो/नाही") | Zero latency, deterministic, covers the numbered-reply path | Misses free text |
| B. LLM zero-shot intent classifier (JSON) | Handles Hinglish, Marathi, Kannada free text | Latency, cost |
| C. Fine-tuned DistilBERT (Aegis-AI lineage) | Offline, fast | Needs labelled data we do not have; declare as prior if reused |
| D. A first, B on fallthrough | Best of both | Two code paths |

**DECIDED (Q12): D.** Keyword/number map first, LLM zero-shot fallback for free text. Whisper for voice notes is a stretch goal only, via a hosted API to avoid GPU setup.

### Safety
Only message the complainant on the contact the original ticket carries (demo: our own registered numbers). Store the hashed ID. Offer "stop" in every message. For the demo, never message real citizens.

## 6. Module 4: Approvals and actions

- `propose_action` creates an `approval` row: `{approval_id, ticket_id, action, verdict_snapshot, status: pending}`.
- `GET /approvals` feeds Ishan's approval queue; `POST /approvals/{id}/decide {decision, note}`.
- On approve, call the Engine's `POST /muni/tickets/{id}/reopen` (or `/escalate`) and then schedule an **outcome check**: after N minutes (demo mode: 30 s) re-run the agent on that ticket and record whether the closure state changed. This is the "outcome verification" loop from the pitch.
- On reject, store the reason. Rejections are training signal for threshold tuning and appear in the eval page as "human override rate".

## 7. Module 5: Audit log

Append-only table where each row stores `prev_hash` and `hash = sha256(prev_hash + canonical_json(event))`. A `GET /audit/verify` endpoint walks the chain and returns OK or the index of the first broken row. It is about 40 lines and gives us a credible "evidence trail" answer for judges. Events logged: run started, each tool call and result, verdict, approval proposed, decision, outbound citizen message, inbound reply.

## 8. Storage **[Q3]**

| Option | Use |
|---|---|
| SQLite (via SQLModel or plain `sqlite3`) | Fastest to set up, a single file, enough for a demo. **Lean.** |
| Postgres (Docker) | Matches the slide stack; adds a service to run |
| Supabase | You know it; hosted; network dependency during the demo |

If the slides say PostgreSQL, we must actually use it somewhere. Put it behind SQLAlchemy so the switch is a one-line URL change, and run Postgres in docker-compose for the deployed version. SQL schemas live as `.sql` files in `agent/sql/` and are reviewed by a human before being applied to any shared database.

## 9. Stack summary

| Layer | Choice | Alternatives |
|---|---|---|
| API | FastAPI, Pydantic v2, SSE via `sse-starlette` | Flask (no native async or SSE ease) |
| Agent loop | Hand-written, JSON tool calling | LangGraph, OpenAI Agents SDK |
| LLM | Hosted API primary, deterministic fallback | Ollama local |
| Vision | `open_clip` or DINOv2-small via ONNX Runtime, `imagehash`, Pillow, `exifread` | Vision LLM |
| Channels | python-telegram-bot, WhatsApp Cloud API (or Twilio) | SMS |
| Store | SQLite, then Postgres for deploy | Supabase |
| Tunnel for webhooks | Cloudflare Tunnel or ngrok | Deployed URL |
| Tests | pytest with a recorded-LLM fixture so agent tests are deterministic | |

## 10. Build plan (hour by hour)

| Time | Task | Done when |
|---|---|---|
| 10:00-11:00 | Repo and service skeleton, create Telegram bot token, WhatsApp developer app, LLM key; publish fixtures for Evidence, Verdict, trace events | Fixtures in `contract/` |
| 11:00-13:00 | Agent loop with **stubbed tools**, fusion math, SSE stream, deterministic planner | Ishan sees a live trace from a fake run |
| 13:00-16:00 | Photo verifier v1 (imagehash + EXIF, then CLIP), call the Engine's real score, approvals table | **Round A:** run the agent on a real scored ticket |
| 16:00-18:00 | Telegram round-trip (send, reply, parse, Evidence), real satellite tool from Soham | One ticket uses 3 tools |
| 18:00-20:00 | Approve to reopen via mock municipal endpoint, outcome check loop, audit chain | Closed loop works |
| 20:00-22:00 | WhatsApp round-trip, LLM planner (Option B) with fallback, guardrail tests | **Round B:** full demo |
| 22:00-02:00 | Calibrate LRs on the shared benchmark, cost-vs-accuracy experiment (agent vs run-everything), Docker, deploy | Numbers for the eval page |
| 07:00-09:00 | Freeze; offline-mode rehearsal | |

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| WhatsApp verification or token trouble | Telegram is the working path; WhatsApp is the stretch with a screen recording as backup |
| LLM API down at venue | Deterministic planner fallback, tested with the network off |
| Agent loops or exceeds budget | Hard step cap (8), code-level budget enforcement |
| Photo model too slow on CPU | Use ViT-B/32 and cache embeddings for demo photos |
| Real closure photos unavailable | Labelled demo set with planted failures; never presented as real municipal data |
| Fusion independence assumption is attacked | We say it is an approximation, show the correlated-pair down-weight, and report calibration on the benchmark |

## 12. Interface checklist
- [ ] Trace events match the contract exactly (Ishan renders them directly)
- [ ] `POST /agent/run/{id}` returns within 200 ms; work happens in the background
- [ ] Every approval carries the full verdict snapshot so the UI needs no extra calls
- [ ] `/audit/verify` passes after a full demo run
- [ ] Shared benchmark file read from `data/benchmark_v1.parquet` (Soham creates it)
