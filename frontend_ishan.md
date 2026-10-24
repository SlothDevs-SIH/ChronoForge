# Frontend (Ishan)

Read `00_contract_and_timeline.md` first. Decision points marked **[Qn]** are in `questions.md`.

## 1. Job to be done

Judges will spend about three minutes on our screen. The frontend has to make three things obvious without anyone explaining them:

1. **The problem is real and measurable.** "Official resolved rate 86%, honest rate X%" on one chart.
2. **The agent actually reasons.** A live trace that picks cheap checks first, uses satellite only when it applies, and abstains when it can't tell.
3. **Humans stay in control.** A clear approval step before anything is reopened.

Everything else is secondary. A second audience is the **public**: a phone-sized "Was it fixed?" page and a public ward view (the proposal promises both).

## 2. Screens (in priority order)

### S1. Ward dashboard (home)
- Left: map of the city coloured by **honest resolution rate** per ward or H3 cell. Toggle between "Official" and "Honest" and let the colours visibly shift. That toggle is the money shot.
- Right: KPI tiles (tickets closed, likely wrongly closed, abstentions, human overrides), a category bar chart, and a "quiet wards wait longer?" scatter.
- Data: `GET /api/engine/wards/stats`, `GET /api/engine/tickets?min_score=0.7`.

### S2. Triage queue
- Table of tickets ranked by `p_false_closure`, with ward, category, closed-in time, top reason chip ("3 repeats in 14 days"), status.
- Filters: ward, category, score range. Click a row to open S3. Bulk "Run agent" button on the selected rows.
- Data: `GET /api/engine/tickets`.

### S3. Ticket detail (the demo centrepiece)
Three columns:
- **Ticket and score**: text, category, map pin, the score as a gauge with calibrated number, SHAP reasons as a short horizontal bar list in plain language.
- **Evidence**: cards for each check (photo, satellite, citizen, human). Photo card: complaint photo vs closure photo side by side with match percentage and flags. Satellite card: before/after slider on the Sentinel chips, with the control z-score and the cloud percentage; ineligible categories show "not checkable from orbit, skipped, cost 0" (do not hide it; the abstention is a feature). Citizen card: the chat bubbles.
- **Agent trace** (right rail): streaming steps with tool icons, a budget bar going down (10, 9, 6 ...), the posterior probability as a line that moves with each piece of evidence, and the final verdict chip. Data: SSE from `/api/agent/stream/{run_id}`.

### S4. Approval queue
- Cards showing the verdict snapshot, the evidence summary and **Approve reopen / Escalate / Reject** buttons with a note field. Approval triggers a toast and S3's status flips to "reopened" via polling. Data: `/api/agent/approvals`.

### S5. Citizen page (mobile first, public)
- Route `/c/:ticketId`: a 3-button "Was it fixed? Yes / No / Partly" in English, Hindi, Marathi and Kannada with a language switcher, plus a photo upload. This doubles as the channel fallback when WhatsApp fails.
- Route `/public`: simple public ward leaderboard of honest resolution, no officer names.

### S6. Evaluation page
- Charts from `GET /api/engine/eval/results`: reliability curve, PR curve, baselines vs LightGBM, per-check precision/recall, abstention rate, cost-vs-accuracy curve for "agent vs run everything". Every chart labelled "synthetic injection" where relevant.

### S7. Audit log
- Table with the hash column and a "Verify chain" button calling `/api/agent/audit/verify`. Small, but judges love a green "chain intact" badge.

Cut order if time runs out: S7 first, then S5's public leaderboard, then S6. S1, S2, S3, S4 must exist for Round B.

## 3. Design direction (so it doesn't look like a template)

SIH-style decks and generic admin dashboards are the default. We want something that looks like a **civic ledger or a newsroom data desk**: calm, dense, honest.

| Direction | Feel | Notes |
|---|---|---|
| A. Civic ledger (**lean**) | Off-white paper background, navy ink, teal for "verified", amber for "uncertain", a muted red only for "likely not fixed". Serif headline (for example Source Serif or Fraunces), sans body (Inter or IBM Plex Sans), tabular numerals | Matches the deck's navy, teal and amber so slides and product feel like one thing |
| B. Control room | Dark theme, glowing map | Looks impressive in a dark hall but harder to read on a projector |
| C. Data-journalism | Big editorial charts, annotations | Great for S1, less suited to dense tables |

Rules: one accent colour per meaning, never decorative. No emoji icons. No purple gradients. Numbers right-aligned in tabular figures. Empty and loading and error states designed, not defaults. Large type for the projector (base size 16-18 px; test at 1280x720).

**DECIDED: Q13 A (React + Vite + TypeScript), Q14 A (MapLibre + deck.gl), Q15 A (civic ledger layout and type) with the exact colours still open.** Put every colour in one `theme.css` set of CSS variables (`--ink`, `--paper`, `--verified`, `--uncertain`, `--alert`) so the palette can change in five minutes. **Q16 decided: demo A (docker-compose on a laptop) and B (deployed) both.**

**Multi-city:** the top bar has a city switcher (Bengaluru, Pune, Mumbai, Synthetic). Each city shows a data-quality badge from the Engine (`real data`, `partial real data`, `synthetic`) next to its name. Add `?city=` to the Engine calls; Soham will accept it.

## 4. Stack options **[Q13, Q14, Q15]**

| Layer | Option A (lean) | Option B | Option C |
|---|---|---|---|
| Framework | **React + Vite + TypeScript** (matches slides, fast HMR, no SSR needed) | Next.js (deploy ease on Vercel, but SSR adds friction with SSE and two backends) | SvelteKit (lighter, but a learning curve under pressure) |
| Styling | **Tailwind + shadcn/ui** components, restyled to direction A | CSS Modules | Mantine or Chakra |
| Map | **MapLibre GL + deck.gl** H3HexagonLayer (matches slides, uses H3 ids directly, free tiles from OpenFreeMap or MapTiler free tier) | Leaflet (you know it, simpler, weaker for many hexes) | Mapbox GL (token required) |
| Charts | **Recharts** for simple, **visx** or **ECharts** for the reliability curve | Chart.js | Plotly |
| Data fetching | **TanStack Query** (polling, caching, retries) | SWR | Plain fetch |
| Realtime | **EventSource** (SSE) for the trace | WebSocket (needs more backend work) | Polling every 1 s |
| State | Zustand | Redux Toolkit | Context only |
| Before/after slider | `react-compare-slider` | Custom | |
| i18n | `react-i18next` for S5 only | Hardcoded 4-language dictionary | |

Deploy: Vercel for `web/`, with backends elsewhere (Render, Fly, or a tunnel to a laptop). **[Q16]** Decide how the demo runs: all on one laptop with docker-compose (safest for the live demo), or deployed (needed for a judge-clickable link). Plan to do both; the laptop is primary.

## 5. How to stay unblocked

1. **Fixtures first.** Soham and Ayush publish fixture JSON in the first hour. Use MSW (Mock Service Worker) so `fetch('/api/engine/tickets')` returns fixtures until the real API is up. Switching to real is flipping an env variable `VITE_USE_MOCKS=false`.
2. **Generate TypeScript types** from the contract's JSON (or from FastAPI's OpenAPI with `openapi-typescript`) so contract drift becomes a compile error.
3. **One API client file** (`web/src/api.ts`) wrapping all calls; no component calls `fetch` directly.
4. **A hard-coded demo mode** (`?demo=1`) that replays a recorded agent run from a JSON file. If the venue Wi-Fi or an API dies during judging, this saves us. Keep it honest: the replay is labelled "recorded run".

## 6. Build plan

| Time | Task | Done when |
|---|---|---|
| 10:00-11:00 | Vite + TS + Tailwind scaffold, theme tokens, MSW, API client, routes | `/` renders fixtures |
| 11:00-13:00 | S2 table and S3 layout with fixture data, map with H3 layer | Click-through works |
| 13:00-16:00 | S1 dashboard with real `/wards/stats`; S3 trace panel wired to SSE; **Round A**: screen recording-ready | Live trace from Ayush's stub |
| 16:00-19:00 | Satellite before/after card, photo card, citizen card, S4 approvals | Full ticket story on one screen |
| 19:00-22:00 | S5 citizen page (mobile), S6 eval page, empty/error/loading states, projector check | **Round B** |
| 22:00-02:00 | Polish, demo mode, accessibility pass (contrast, keyboard), deploy | URL works from a phone |
| 07:00-09:00 | Freeze, rehearse the click path twice | |

## 7. The demo click-path (rehearse it)

1. S1: toggle **Official vs Honest**. The map shifts. "Here is the gap."
2. Click the worst ward, go to S2, pick the top ticket.
3. S3: show the score and reasons. Press **Run agent**.
4. Watch the trace: cheap photo check, then satellite (or "skipped, not checkable"), then a citizen ask. Posterior line moves.
5. Telegram or WhatsApp on a phone buzzes. Reply "No". The citizen card updates live.
6. Verdict chip: likely not fixed. S4: **Approve reopen**.
7. Ticket status flips on the simulated municipal system. Agent schedules the outcome check.
8. S6: "Here is how we know it works, and here is where it doesn't."

Total about 3 minutes. Vedashree writes the voiceover (see `research_vedashri.md`).

## 8. Risks

| Risk | Mitigation |
|---|---|
| deck.gl H3 layer fights with TypeScript or bundle size | Fall back to a MapLibre fill layer with GeoJSON polygons from `h3-js` |
| SSE through a proxy buffers events | Send a periodic comment ping; disable proxy buffering; fallback to polling |
| Projector washes out colours | Test on a bad projector or screen-share; use high-contrast text |
| Contract changes late | Types generated from the contract; breakage shows up at compile time |
| Map tiles blocked offline | Use a plain background with just hex polygons if tiles fail |
