# TrueClose web app

React 18, TypeScript, Vite, React Router, TanStack Query. Plain CSS (no Tailwind). Supabase Auth in the browser; both services verify the token.

## Run it locally

```bash
cd web
npm install
npm run dev          # http://localhost:5173 (the Vite proxy sends /api/engine and /api/agent to the local services)
```

`npm run dev` loads `.env.development`, which sets `VITE_AUTH_DISABLED=1`: sign-in is skipped and every page opens as a local admin.
Use that only with backends started with `AUTH_REQUIRED=0` (the default). Start them from the repository root:

```bash
cd engine && uvicorn app.main:app --port 8001
cd agent  && AGENT_USE_STUBS=0 PUBLIC_DEMO_RUNS=1 uvicorn app.main:app --port 8002
```

## Environment variables (`.env.example`)

| Variable | Meaning |
|---|---|
| `VITE_ENGINE_URL`, `VITE_AGENT_URL` | Service base URLs in production (leave unset locally). The services must list the site in `CORS_ORIGINS` |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Supabase project. Without them a production build says "Sign-in isn't set up yet" |
| `VITE_AUTH_DISABLED` | `1` skips sign-in for local demos. Never set in production |

## Scripts

| Script | What it does |
|---|---|
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (typescript-eslint, react-hooks) |
| `npm test` | Vitest unit and component tests, with MSW mocks (tests only) |
| `npm run test:e2e` | Playwright against the Vite dev server in `--mode e2e` with Supabase and API calls mocked; includes axe-core scans. Uses the installed Chrome |
| `npm run gen:api` | Regenerates `src/api-schema/*.d.ts` from `engine/openapi.json` and `agent/openapi.json` |
| `npm run build` | Type-check and production build |

`src/lib/contract.test.ts` fails if the web client calls an endpoint that is missing from the exported OpenAPI specs.

## Routes

Public: `/`, `/how-it-works`, `/evaluation`, `/platform` (System status), `/reply/:token`, `/auth/login`, `/auth/official`, `/auth/register`, `/auth/forgot-password`, `/auth/pending`.
Officers and admins: `/dashboard`, `/triage`, `/ticket/:id`, `/approvals`, `/audit`. Admins: `/admin`. Citizens: `/my-tickets`.
The guards only shape the experience; the services enforce roles on every request.

## Ticket photos

Cards show a photo only when one is known: the twelve demo tickets carry their own, and `public/assets/ticket-photos/index.json`
maps other ticket ids to files (see the README in that folder). Everything else says "No photo on record".

## Hero video

`python scripts/make_hero_video.py <repo root> <ffmpeg>` rebuilds `hero.mp4`, `hero.webm` and the poster from `frontend_comp/`.
