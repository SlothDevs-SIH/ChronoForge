# TrueClose implementation plan (frontend recovery, integration, honest demo)

Written 24 Oct from an audit of the real repository. Everything below was checked in the repo or by running it; items I could not check are marked **not verified**. The earlier brief (`frontend_comp/ASTRA_FRONTEND_IMPLEMENTATION.md`) assumed things that do not match the repository; the differences are listed in section 2.

## 1. Verified architecture

| Part | Reality |
|---|---|
| Repo | `integration` branch, equal to `main` plus later work. Other people's uncommitted frontend edits exist in `web/` and `frontend_comp/` and are preserved |
| Frontend | **Vite 5 + React 18 + TypeScript**, React Router 6, TanStack Query 5. No Tailwind, no Next.js, no animation library, no UI kit, no `@/` alias. Plain CSS with variables in `web/src/theme.css`. Dev port 5173 |
| Engine (`engine/`, port 8001) | FastAPI + DuckDB over Parquet, about 822,800 tickets in 5 cities (Bengaluru, Mumbai real; Pune, Sandbox synthetic; `demo` = 12 synthetic tickets with photos). Scorer, satellite verifier, simulated municipal endpoint |
| Agent (`agent/`, port 8002) | FastAPI + SQLite (Ayush). Guarded planner, photo/satellite/citizen tools, approvals, audit chain, SSE trace. Needs its own virtual environment (`agent/requirements.txt`) |
| API from the browser | Vite proxy: `/api/engine/*` to 8001, `/api/agent/*` to 8002. SSE is named events (`event: trace`, `event: end`) |
| Contract | `contract/README.md`, `INTEGRATION.md`, `PROJECT_OVERVIEW.md` |
| Missing files | **`front-end.md` does not exist anywhere in the repo.** The Astra brief is in `frontend_comp/`. **The Cult UI component source is not in the repo**, only the brief's description of it |
| Assets (`frontend_comp/`) | `TrueClose_ Verified Civic Solutions.png` (design comp), `gemini_generated_video_*.mp4`, `frontend_ishan.md` (the older frontend brief), the Astra brief |
| Tests | engine 166, agent 105, web type-check. No frontend unit or browser tests existed |
| Browser verification | The Claude-in-Chrome extension is **not reachable** from this environment (two failed attempts). Verification uses Playwright driving the installed Chrome instead |

## 2. What is wrong now (verified)

**Backend "not responding" (two independent causes, both reproduced)**
1. Engine and Agent were simply not running (nothing listening on 8001/8002).
2. **Vite proxy used `localhost`.** Node resolves it to IPv6 `::1`; uvicorn listens on IPv4 `127.0.0.1` only, so every proxied call got an empty HTTP 500 while `curl localhost:8001` still worked (curl falls back to IPv4). Fixed: proxy targets are `127.0.0.1` (overridable with `ENGINE_PROXY` / `AGENT_PROXY`). Proven through a host Vite on 5174: Engine, Agent and the SSE stream all work.
3. The Vite on port **5173 is not on this machine's loopback**: its listener belongs to a VM port-forwarder. From inside a VM, `127.0.0.1:8001` is the VM's own loopback, so that server cannot reach host backends. It was left untouched; a host dev server is used instead.

**Landing page (screenshot and measurements, 1440x900)**
- 3,884 px tall (four screens of scrolling). The brief wants none on desktop.
- Hero is a **still image**, not the video; HTML cards sit on top of baked-in cards from the image and collide; right-hand cards are cut off.
- **Invented claims**: "3x more accountable", "40-60% faster triage", "Trusted for cleaner, more accountable cities", an "87%" risk, a "98% match" and "2 min ago" evidence panel. All break our rule that every number is real, sourced or labelled.
- "See how it works" is an in-page anchor (the brief requires a separate page). Template tells: tracked all-caps eyebrow, an arrow on every button, glyph characters used as icons.
- Console: a 404, React Router future-flag warnings.

**App pages (read from source)**
- Ticket detail shows `p_false_closure` as a big percentage for every score type, including Bengaluru's rank prior (which is **not** a probability) and Mumbai's flag.
- The "Evidence register" is static text: it never shows the photos, the satellite result, the agent verdict or the approval.
- The overview's "Ward signal map" is a CSS placeholder; its tiles include "Human control 100%".

**The supplied video** (inspected with ffmpeg): 1280x720, 10.0 s, H.264, 24 fps, **has an audio track**, 6 MB. It is AI-generated and its **baked-in text is garbled** ("CLOSED BIGGEE MOAN TIXED", "Photo Veeedback", "Gebrady", "Cloans not collete to egency feature"); it also bakes in its own headline, logo and a bottom icon bar. The camera is locked off. It cannot be shown unmodified.

## 3. Confirmed design requirements

- Palette and type exactly as in `web/src/theme.css` (Forest Intelligence: Deep Forest `#163D32`, Evergreen `#245747`, Electric Lime `#C5F36A`, Warm Ivory `#F7F7F0`, Charcoal `#18211D`; Manrope for headings, Inter for text; semantic success/warning/danger/neutral). About 70% ivory and white, lime as a rare accent.
- Landing: one viewport on desktop, video-led, headline **"Closed should mean fixed."**, two buttons to two different routes, no marketing stack underneath.
- The brief wins over general taste where they conflict: the headline keeps its single accented word ("fixed") because the brief and the comp require it.
- Honesty rules (from `INTEGRATION.md`): no invented numbers or partners; simulated and synthetic things are labelled; Bengaluru and Mumbai scores are bounded priors, not probabilities; nothing reopens without a human approval; satellite checks only where they can see the problem.

## 4. Page and routing structure

| Route | Purpose |
|---|---|
| `/` | Landing: video hero, headline, two actions |
| `/how-it-works` | The six-step verification story as an interactive explainer, with what is real, simulated and not built |
| `/platform` | Honest exploration: live connection status, the data that is actually loaded per city, and a real verification you can run on the demo tickets |
| `/dashboard`, `/triage`, `/ticket/:id`, `/approvals` | Existing application (kept; fixed where listed in section 2) |
| `*` | Not-found page with links |

## 5. Component decisions (Cult UI)

The Cult UI source was not supplied in the repo, so I reviewed only the brief's description and did not copy code I have not seen. Nothing is installed.

| Component | Decision |
|---|---|
| HaloProgress | **Reject**: the agent budget bar and a determinate step indicator already cover it; a fake progress animation would misrepresent real work |
| HaloToast | **Adapt** (own small implementation): needed for approve/reject results. `role="status"`, shown only after the API call actually succeeds or fails |
| Dock / DockAnimation | **Reject**: no real need; it is ornamental |
| FloatingPanel | **Reject**: its demo actions only log to the console and there is no matching workflow |
| VideoSection | **Reject**: native `<video>` is enough; no external player dependency |
| ExpandableScreen | **Reject**: there is no complaint-intake workflow in the product, and the demo is a waitlist with fake testimonials |

New dependencies: none planned. Icons are inline SVG. Motion is CSS only (one orchestrated hero entrance, step transitions that answer a click), disabled under `prefers-reduced-motion`.

## 6. Hero video treatment

Source is never modified. The first clip supplied was replaced on 24 Oct by `frontend_comp/gemini_generated_video_28ed53ce.mp4`, also AI-generated, whose middle shows UI cards, a slide and a monitor with garbled text. `web/scripts/make_hero_video.py` uses only its clean aerial city shot (8.45 to 10.0 s): two small hex-code tags are covered with a patch cloned from nearby scenery, the generator's sparkle mark is blurred, and the shot plays forward then backward, slowed 2x, for a seamless 6 s loop with no audio (`hero.mp4` about 780 KB, `hero-poster.jpg`). One `<video>` element fills the page, softened under a left-side gradient for the headline; pause/play button, poster fallback, reduced motion shows the poster only. Labelled "Concept render. Not live data."

## 7. Implementation sequence

1. Fix the proxy and run the services (done).
2. Process the video (done).
3. Foundation: split CSS (tokens, app, public pages), SVG icon set, toast, connection-status hook, route table with a not-found route.
4. Landing, then `/how-it-works`, then `/platform` (live data, demo verification with the real agent, demo photos served by the Engine).
5. Fix the application pages (score semantics, evidence register wired to real data, real overview instead of the placeholder map, remove invented tiles).
6. Verify: type-check, production build, Playwright screenshots at four viewports, console and network errors, keyboard and reduced-motion checks, route refresh, API flows.
7. Update this file with results and remaining gaps.

## 8. Acceptance criteria

- Desktop 1440x900 and 1280x720: landing document height equals the viewport (no scrolling).
- Video visible and playing, no audio, poster fallback, pause control, reduced-motion respected.
- "See how it works" opens `/how-it-works`; "Explore the platform" opens `/platform`; both render and survive a hard refresh.
- No invented figures anywhere; every number comes from the API or a cited document.
- Connection status reflects real checks (connected, connecting, offline, error) and the demo run uses the real agent.
- Type-check and production build pass; no console errors on the main routes.
- Contrast 4.5:1 for text, 3:1 for UI; visible focus; 44 px targets; semantic landmarks; status never conveyed by colour alone.

## 9. Blockers and dependencies

- Browser-extension automation is unavailable here (Playwright with installed Chrome is used).
- The Agent needs its own virtual environment; a fresh clone must run `pip install -r agent/requirements.txt`.
- The photo "still broken" check needs CLIP (about 2 GB); it is off, so the demo cannot show it. The UI says so.
- The Vite server on 5173 runs in a VM and needs `ENGINE_PROXY` / `AGENT_PROXY` pointing at an address reachable from the VM.
- Telegram needs Ayush's token and a registered chat; WhatsApp is parked.

## 10. Skills and tools used

Loaded and applied: `frontend-design` (one bold element, avoid template tells, plan then critique), `ui-ux-pro-max` (accessibility first, touch targets, SVG icons, performance, reduced motion), `design:accessibility-review` (WCAG 2.1 AA checks), `design:ux-copy` (verb-first CTAs, errors that say what and how to fix, sentence case), `dataviz` (single-hue bars, direct labels, a table alternative), `vercel:react-best-practices` (no components inside components, derived state, no needless effects). Tools: ffmpeg (bundled), Playwright with installed Chrome, the repo's own test suites. **Not available:** the Claude-in-Chrome extension.

## 11. Results (24 Oct, after implementation)

**Done and verified** (Playwright with installed Chrome, 1440x900, 1280x720, 820x1180, 390x844; type-check and production build clean; Engine tests 167 pass):
- `/` is one viewport on desktop (document height 900 at 1440x900, 720 at 1280x720), video background (no audio, poster, pause/play button, reduced motion shows the poster paused), headline and two buttons to `/how-it-works` and `/platform`. All invented claims removed.
- `/how-it-works`: six-step tabbed explainer (arrow-key navigation), real/simulated/not-built tags, live ticket count from the Engine, interactive evaluation example using the Agent's configured likelihood ratios, labelled as an example.
- `/platform`: live Engine and Agent status (5 s polling, offline panel with start commands), per-city cards from `/cities`, real agent run on the demo tickets (verified: 6 trace events and a verdict through the proxy).
- New Engine route `GET /media/demo/{ticket}/{before|after}.jpg` (only files the ticket row names, inside `demo/photos/`; test added).
- App pages: ticket score shown per score type (percent only for synthetic calibrated; rank for Bengaluru; flag for Mumbai), evidence register wired to photos, stored satellite results, agent trace and approval; overview placeholder map replaced by a real reopen-rate-by-category chart with a table alternative; "Human control 100%" replaced by the live pending-approval count; toasts after real approve/reject/run results; not-found route; favicon; router future flags (no console warnings).
- No new dependencies. Cult UI: HaloToast adapted as `components/Toast.tsx`; the rest rejected as planned.

**Remaining gaps**
- Nothing is committed or deployed. The Claude-in-Chrome extension was never reachable, so there was no real-browser run beyond Playwright.
- Display fonts (Manrope, Inter) load from Google Fonts; offline they fall back to system fonts.
- A faint seam remains at the top edge of one patched card area in the hero video (source is AI-generated; see section 6).
- No automated frontend tests (type-check, build and the Playwright checks above only). Photo "still broken" check needs CLIP and stays off.
- Port 5173 is a VM-hosted dev server that cannot reach host backends; use `http://localhost:5174` or set `ENGINE_PROXY` / `AGENT_PROXY`.

**Added later the same day:** `/evaluation` (read from `/eval/results`), `/audit` (hash chain and verify badge), Engine `GET /wards/map` with an SVG ward map and an Official / After-citizen-reopens toggle. Still not built: the citizen reply page (needs a ticket-bound reply endpoint in the Agent), a basemap under the ward map, a before/after slider for satellite chips, frontend unit tests.
