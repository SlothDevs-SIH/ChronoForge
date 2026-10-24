# TrueClose: next steps (backend, frontend, sign-in)

Written 24 Oct. This is the checklist for the three prompts you pasted: the backend/DevOps prompt, the frontend prompt, and the 21st.dev sign-in component. Nothing here is built yet. Each item is a checkbox so it can be ticked off as it lands.

Rules that apply to all of it (from the prompts and from this project):
- Small, reviewable commits on a feature branch. Do not rewrite the stack. Do not rename existing routes.
- Do not claim anything works unless it was run. Report pass and fail honestly.
- **Ask before:** destructive schema changes, switching databases, changing any likelihood ratio, prior, threshold or verdict logic, deleting data, renaming routes.
- No secrets in code. Document every variable in `.env.example`. If a credential is missing, build the boundary and list exactly what is needed.
- Organisation rules for Claude Code: it does not log in to other machines with ssh, it does not run INSERT, UPDATE, DELETE or DDL against any database (it writes the SQL and you run it, SELECT is fine), and it does not change network settings. This matters for the Postgres work below.
- WhatsApp stays parked until later.

---

## 1. What is verified today

Checked on 24 Oct against the live site and the repo.

| Claim in the prompts | Result |
|---|---|
| In production, `/api/engine/*` and `/api/agent/*` return `index.html` with HTTP 200 | **Confirmed.** `https://trueclose-neon.vercel.app/api/engine/health` and `/api/agent/health` both return `200 text/html`. Cause: `web/vercel.json` has one catch-all rewrite (`/((?!assets/|favicon.svg).*)` to `/index.html`) and no backend is deployed, so `/api` falls into the SPA. That rewrite was added to make deep links like `/platform` survive a refresh. |
| No backend is deployed | **Confirmed.** Only `web/` is on Vercel (project `trueclose`, team `peer-training`). |
| The dev proxy is the only thing routing `/api` | **Confirmed.** `web/vite.config.ts` proxies `/api/engine` to `127.0.0.1:8001` and `/api/agent` to `127.0.0.1:8002`. |
| The UI exposes ports and CLI commands | **Confirmed.** Port numbers and `uvicorn` / `python -m app.ingest demo` text appear in `Platform.tsx`, `Approvals.tsx`, `AuditLog.tsx`, `Evaluation.tsx` and `TicketDetail.tsx`. |
| The Agent uses local SQLite and the Engine uses local files | **Confirmed.** Agent: `AGENT_DB` defaults to `agent.db`. Engine: DuckDB over Parquet in `data/warehouse` (not in git), about 822,800 tickets, plus `data/warehouse/status_overrides.json` for municipal status changes. |
| The web app has no Tailwind, shadcn, lucide-react or `@/` alias | **Confirmed.** Plain CSS variables in `src/theme.css` and `src/public.css`. |
| "Open the app" links to `/dashboard` and loads without sign-in | **Confirmed.** There is no auth anywhere (Engine, Agent or web). |

Not yet checked (do these first in each prompt's step 1): the hero glitch at 320, 480, 648, 768, 1024 and 1440 px and in a half-width window. Earlier checks covered 390, 820, 1280 and 1440 only.

---

## 2. Decisions you need to make before work starts

These come from places where the prompts conflict with what exists, or where they say "ask first".

1. **Hosting for the two Python services.** The prompt allows Render, Railway, Fly or Cloud Run. Recommendation: Render or Railway with Dockerfiles, because the Engine needs a large local dataset and long-lived processes. Vercel functions do not fit (the Engine loads Parquet through DuckDB; the Agent holds SSE streams for up to minutes). Which host, and which account?
2. **Switching to Postgres is a database switch, so it needs your yes.** Today: Engine = DuckDB + Parquet (800k tickets, read-heavy, fast), Agent = SQLite. Options: (a) Postgres for the Agent only (users, roles, approvals, audit, verification runs) and keep the Engine's Parquet as a read-only dataset shipped with the image or object storage; (b) move everything to Postgres. Recommendation: (a). Moving 800k tickets and the scorer queries to Postgres is a large, risky change with no user-facing gain.
3. **Auth provider.** Default in the prompt: Supabase Auth (also gives Postgres and storage in one place). Clerk is acceptable. Which one, and who owns the account?
4. **Landing-page buttons conflict with an earlier decision.** The frontend prompt wants one primary "Open the app" and one secondary "How it works", with "Explore the platform" removed and `/platform` moved to a footer link called "System status". Your earlier master prompt asked for "See how it works" and "Explore the platform" as the two hero buttons. Which wins? (Assumed below: the new prompt.)
5. **Tailwind and shadcn.** The sign-in component is written in Tailwind utility classes and imports from `@/components/ui`. The web app has neither. Either add Tailwind v3 or v4, `@/` alias and shadcn structure to the Vite app, or rewrite the component in the existing plain CSS. Adding Tailwind next to the current CSS risks style clashes; recommendation: add Tailwind scoped to the auth pages only, or rewrite in plain CSS using the existing tokens. Which?
6. **Social login buttons.** The component ships "Continue with Google" and "Continue with GitHub". Do you want social login at all? If yes, those need provider setup in the auth dashboard. If no, remove them.
7. **Citizen role versus the product's scope.** TrueClose audits tickets cities already closed and is not a grievance-intake app. Citizens today only reply to a verification question (via Telegram). The prompt adds citizen self-registration, "My checks" and photo upload on the web. Confirm this is wanted, and how a citizen is linked to a ticket they filed in an external city system (the external ticket id? a Telegram-registered contact?).
8. **Officer onboarding.** Invite-only or admin-approved? Who is the first admin and how is it created (a seed script run by you)?
9. **Hero footage licence.** The prompt requires licensed footage with the source recorded. The current hero is AI-generated (Gemini) from `frontend_comp/`, with its sparkle mark and tags covered. Keep it with a note, or source stock footage? Also the prompt asks for webm plus mp4 at 2.5 MB or less; the current mp4 is about 780 KB.
10. **Colour tokens.** The prompt lists forest `#173D32` and primary `#245B45`; the repo uses `#163D32` and `#245747`. Switch to the prompt's values, or keep the current ones?
11. **Anything that changes verification display wording.** The prompt says "ask before changing verification display logic" and forbids "Verified fixed" without an uncertainty note. The ticket page currently shows the Agent's verdict states; confirm the wording change.

---

## 3. Backend and DevOps checklist

### P0: make the deployed app work
- [ ] 1. Reproduce: curl prod `/api/engine/health` and `/api/agent/health` (done once, see section 1) and record in the PR.
- [ ] 2. Dockerfiles for Engine and Agent (separate images; both packages are named `app`, so they must stay in separate environments). Start commands. Pick the host (decision 1) and justify it in the PR.
- [ ] `/health` (liveness) and `/ready` (dependencies reachable: database, warehouse, storage) on both services, JSON with `application/json`. The Agent already has `/health`; the Engine has `/health` with `mode`.
- [ ] 3. Postgres via the repo's migration tool or Alembic (decision 2). **Claude writes the migration SQL and gives it to you to run; it does not run DDL or DML itself.**
- [ ] Private object storage for images (demo photos, citizen uploads), served only through short-lived signed URLs. Today the demo photos come from `GET /media/demo/...` on the Engine.
- [ ] 4. Vercel rewrites for `/api/engine/:path*` and `/api/agent/:path*` to the service URLs, placed **before** the SPA catch-all in `web/vercel.json`. Service base URLs from environment variables. CORS allowlist (the Engine currently allows `*`).
- [ ] SSE through the Vercel rewrite: confirm `/api/agent/agent/stream/{run_id}` still streams (or call the Agent directly with CORS).
- [ ] 5. Demo ingest idempotent and run on deploy. Every record keeps its `real` / `partial` / `synthetic` label. (Today `python -m app.ingest demo` loads 12 tickets; running it twice must not duplicate or reset approvals.)
- [ ] The 800k-ticket warehouse is not in git. Decide how the deployed Engine gets it (baked into the image, or pulled from object storage at start).

### P1: authentication and authorisation (server side only)
- [ ] 6. Managed provider (decision 3). Verify the JWT in **both** services with middleware. No hand-rolled password storage.
- [ ] 7. Roles `citizen`, `officer`, `admin` in a server-side table, never in client-editable metadata. Citizens may self-register. Officers are invite-only or admin-approved (decision 8). A `pending` state that grants nothing. Supervisor and auditor roles are deferred.
- [ ] 8. Permission matrix enforced per endpoint and tested:

| Role | Can |
|---|---|
| citizen | read own evidence and replies; submit a citizen reply; attach evidence; request a reopen |
| officer | read the triage queue; approve or reject reopens |
| admin | manage users and approvals; view system health |
| pending, logged out | nothing privileged |

- [ ] 9. Approvals: a reopen is never automatic. Record actor, timestamp and reason. Keep the existing Approvals semantics (the Agent proposes, a person decides, the decision is recorded in the audit chain, approve calls the simulated municipal endpoint).
- [ ] Existing admin token (`ENGINE_ADMIN_TOKEN`, `require_admin` on the Agent) is replaced or sits behind the new roles.

### P1: verification engine (preserve, do not reinvent)
- [ ] 10. **Do not change any ratio, prior, threshold or verdict logic.** Move hardcoded values into a versioned config file (current values: photo duplicate 8, far GPS 4, stale 3, clean 0.5; citizen no 6, partly 2, yes 0.3, silence 1.2; satellite 0.45 / 1.25; thresholds 0.75 and 0.25; budget 10; costs photo 1, citizen 2, satellite 3, human 10). Ask before touching any of them.
- [ ] 11. Persist each verification run: ticket id, inputs, prior, each check (performed or skipped, with the skip reason), ratio applied, posterior, config version, timestamp, data provenance. Add `calibrated: false` to the output while ratios are unmeasured.
- [ ] 12. Keep `closure_claimed` (from the city), `verification_verdict` (engine) and `review_state` (human) as three separate fields. Derive "inconclusive" and "not performed" only from existing check outcomes. Unavailable satellite imagery is "skipped", never evidence.
- [ ] 13. Never fabricate scores, image comparisons or satellite observations. A service down returns a pending state with a reason. (The Agent already refuses to invent a prior in strict mode.)

### P1: citizen evidence
- [ ] 14. Photo-attach endpoint: JPEG, PNG, WebP only; check magic bytes; size cap (for example 8 MB); content hash; idempotency key; strip EXIF GPS from stored copies; use location server-side only, for the existing location check.
- [ ] 15. Matching needs an explicit ticket id. Otherwise return ranked candidates for the user to confirm. Never auto-attach below a threshold.
- [ ] 16. A citizen photo gets **no** likelihood ratio by default: stored for human review. The citizen reply (yes, partly, no) uses the existing ratio.
- [ ] A ticket-bound citizen reply endpoint on the Agent (today replies arrive only through the Telegram webhook). This also unblocks the planned mobile citizen page.

### P2: hygiene
- [ ] 17. Consistent error body `{error:{code,message}}`, request ids, cursor pagination, rate limits on auth and upload, structured logs, append-only `audit_events` table (the Agent's hash-chained audit already exists and must keep verifying).
- [ ] 18. pytest in CI: permission matrix, upload validation, status transitions, idempotency, verification determinism with fixtures for (a) clear success, (b) satellite skipped, (c) all checks skipped. CI does not exist yet: add a workflow.
- [ ] OpenAPI spec exported from both services (the frontend client is generated from it).

### Backend deliverables to hand back
Bugs and root causes; files changed; OpenAPI; permission matrix; env vars and migrations; deploy steps; test results; what is still blocked.

---

## 4. Frontend checklist

Precondition: build against a typed client generated from the backend OpenAPI spec. MSW mocks only in tests and Storybook, never in production code. If the backend is not live, show honest error states and no fake data.

### P0: robust data layer
- [ ] 1. API client checks `response.ok` **and** `Content-Type`. A non-JSON response becomes a typed error, not a `SyntaxError` shown to people. (This is the exact failure on the live site today: `/api` returns HTML.) Today `web/src/api.ts` only checks `ok`.
- [ ] 2. Every list or page: skeleton loading, empty state, error with retry. Remove port numbers and CLI instructions from user-facing copy (files listed in section 1). Move diagnostics (connection status, start commands) to an admin-only status view.

### P0: hero and layout
- [ ] 3. Reproduce the glitch first at 320, 480, 648, 768, 1024, 1440 and a half-screen window; find the root cause (likely `100dvh`, absolute positioning, or object-fit on the 117%-tall video); fix the cause.
- [ ] 4. Video: absolute full-bleed, `object-cover`, muted, `playsInline`, loop, `preload="metadata"` (today `auto`), poster always rendered, `onError` falls back to the poster, reduced-motion **and save-data** show the poster only (save-data is not handled today), keep the pause control, scrim keeps text at 4.5:1 or better, webm plus mp4, 2.5 MB or less, footage source recorded (decision 9).
- [ ] 5. No horizontal overflow at any width.

### P0: call-to-action hierarchy (assumes decision 4)
- [ ] 6. Hero: one primary "Open the app" and one secondary "How it works". Remove "Explore the platform" from the hero. Remove the repeated CTA blocks at the bottom of `/platform` and `/how-it-works` (keep one end-of-page CTA only where it adds value). Move `/platform` to a footer link labelled "System status". Do not rename the route.

### P1: sign-in screens and route guards
- [ ] 7. `/auth/login`, `/auth/register`, `/auth/forgot-password`. Try the 21st.dev command first (`npx shadcn@latest add "https://21st.dev/r/preetsuthar17/modern-stunning-sign-in"`) and check it has no Next-only imports (`next/link`, `next/image`). See section 5 for the component given. Restyle to the TrueClose green tokens; wire it to the backend's auth provider.
- [ ] 8. A separate "Official sign-in" for officers with no self-signup. A "pending approval" screen. Show forgot-password only if the backend has an email provider.
- [ ] 9. Guards: logged out goes to `/auth/login?next=<path>`; expired session goes to login with a message; wrong role gets a 403 page; unknown route gets the 404 page (exists today). Frontend guards are UX only; the servers enforce.

### P1: role views (build on what exists)
- [ ] 10. Officer: existing Overview, Triage queue and Approvals, plus search, filter, sort and pagination (city, status, risk, age).
- [ ] 11. Citizen: "My checks" with replies given and evidence uploaded; a reply flow (yes, partly, no); photo upload with preview, type and size validation, progress, and a candidate-confirmation step when the ticket cannot be matched. Never claim an uploaded photo proves a fix.
- [ ] 12. Admin: user list, officer approvals, system status.
- [ ] 13. Ticket detail: before and after photos, a checks table (performed versus skipped, with reasons), odds multipliers, prior to posterior, a visible note that priors are not measured on real closures, real or synthetic badge, a timeline. Use the API's verdict, never recompute scores in the browser. No absolute "Verified fixed" without the uncertainty note. (Today the ticket page shows the trace and the score but not a checks table or a timeline; the How it works example does compute odds client-side, but it is labelled as an example, not a ticket result.)
- [ ] 14. Charts only from API data; empty state otherwise. Never invent statistics. (Existing charts already read from the API.)

### P2: design system and quality
- [ ] 15. Green tokens as CSS variables or a Tailwind theme (decision 10). Status chips with icon and text, not colour alone. Visible focus. Labelled forms. Keyboard-reachable CTAs. No glassmorphism, neon or decorative floaters. (The hero currently uses a backdrop blur behind the left text; the prompt says no glassmorphism, so confirm or replace with a plain scrim.)
- [ ] 16. Tests: Vitest for components; Playwright for guard redirects, hero at the widths above, video blocked or failing, reduced motion, auth flows; axe-core on key pages. Run lint, typecheck and build. Today there are no frontend unit tests and no lint script.

### Frontend deliverables to hand back
Bugs and root causes; files changed; screenshots at the test widths; accessibility, test and build results; what is blocked by the backend.

---

## 5. The sign-in component you pasted (`sign-in-page.tsx`)

What it is: a split-screen login page (image left, form right) using Tailwind classes, `lucide-react` icons and `react-router-dom`, exported as `LoginPage`. Needs `lucide-react` and `react-router-dom` (the app already has the router).

What does not fit as pasted:
- **Needs Tailwind, shadcn structure and the `@/` alias.** None exist in `web/` (decision 5). The demo imports `@/components/ui/sign-in-page`, so the file belongs in `web/src/components/ui/`, which is the folder shadcn expects; the alias needs `vite.config.ts` and `tsconfig.json` changes.
- **`'use client'`** is a Next.js directive. It is harmless in Vite but should be removed.
- **It does nothing yet.** `handleSubmit` only logs the form to the console, including the password. It must call the auth provider instead and never log credentials.
- **Off-palette.** Blue gradient background, blue links, a black button and a generic remote image. Restyle to the green tokens and use a local, licensed image (the prompt suggests Unsplash stock; record the source and licence).
- **Accessibility gaps.** Labels are not tied to inputs (`htmlFor` / `id`), the back button and the show-password toggle have no accessible names, `h-screen w-screen` breaks on mobile browsers with dynamic toolbars, focus rings are only `ring-2` with no offset, and there is no error message area.
- **Routes it assumes.** It navigates to `/` and `/signup`; this app uses `/auth/register`, so update the links.
- **Forgot password** is a button with no handler. Show it only if the provider has email set up.
- **Social buttons** (decision 6).
- **Officer sign-in** needs its own variant without the sign-up link.

Integration steps once decisions 3 and 5 are made:
1. Install `lucide-react` (and Tailwind plus shadcn setup if chosen).
2. Add the component under `web/src/components/ui/`, fix the issues above.
3. Add the three `/auth/*` routes and the "Official sign-in" route in `App.tsx`.
4. Wire submit to the auth provider; store the session; add a guard component around `/dashboard`, `/triage`, `/ticket/:id`, `/approvals`, `/audit`.
5. Send the access token on API calls; show the pending-approval, 403 and expired-session screens.

---

## 6. Suggested order (smallest steps that unblock the rest)

1. Answer the decisions in section 2.
2. Backend: Dockerfiles, `/health` and `/ready`, deploy Engine and Agent, fix the Vercel rewrite order. This alone makes the live site work for the demo set.
3. Frontend: API client content-type check and honest error states; remove ports and CLI text; hero fixes and CTA changes.
4. Backend: Postgres for the Agent (SQL handed to you to run), object storage and signed URLs.
5. Auth: provider, middleware in both services, roles table, permission tests; then the frontend auth screens and guards.
6. Verification config file, persisted runs, `calibrated: false`.
7. Citizen evidence endpoint and the citizen views.
8. Admin views, officer filters and pagination, tests, CI.

---

## 7. What is blocked until you provide it

- A hosting account for the Engine and Agent (and the plan size that can hold the warehouse).
- Auth provider project (URL, anon and service keys, JWT secret) and, for password reset, an email provider.
- Object storage bucket and credentials.
- A decision on where the 800k-ticket warehouse is stored for the deployed Engine.
- Agent keys already in `agent/.env` (Gemini, Telegram) set as host environment variables. Claude cannot enter these for you.
- Footage source or licence for the hero, and a licensed image for the sign-in page.
- Someone to run the Postgres migration SQL that Claude writes.
