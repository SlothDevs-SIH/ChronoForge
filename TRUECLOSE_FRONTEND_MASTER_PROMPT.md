# TrueClose frontend master prompt

Build phase only. **Do not run tests, lint or builds in this phase** (testing is a separate pass). Do not touch `engine/` or `agent/`.

## Context
TrueClose checks that closed civic complaints were really fixed. Web app in `web/` (React 18, TS, Vite, React Router, TanStack Query, plain CSS, Supabase Auth). The backends are done; the contract is `contract/AUTH_AND_DEPLOY.md`.

## Decisions already made (do not re-ask)
Plain CSS, current green palette. One button on public pages. Full 10 s hero video. No social login. Citizens only see their linked tickets (no creation, no uploads from the UI). Officers are admin-approved; first admins come from `ADMIN_EMAILS`. Engine stays on DuckDB/Parquet; Postgres is for the Agent only. Host on Render, auth on Supabase.

## Rules
- Never invent data, photos or scores. Show "No photo on record" or an empty state instead. Label real / partial / synthetic.
- Never change a likelihood ratio, prior, threshold or verdict. Nothing reopens without human approval.
- Match the surrounding code: naming, comment density, plain CSS classes already in `theme.css`, `queue.css`, `public.css`, `cutout.css`.
- Every new list or panel needs loading, empty and error states (`components/States.tsx`).
- Keep other people's uncommitted files out of commits (`frontend_comp/`, `frontend_ishan.md`, `trueclose-hero.jpg`).

## Work list
1. **Gaps found in the audit**
   1. `api.ts`: add `ticketEvidence(ticketId)` and `evidenceUrl(evidenceId)` for the Agent's `GET /tickets/{id}/evidence` and `GET /evidence/{id}/url`.
   2. Ticket page, officer side: a "Citizen reply link" panel (language en/hi/mr/kn, creates a link with `api.replyLink`, shows the full URL with a copy button and the expiry).
   3. Ticket page, officer side: a "Citizen photos" list from the evidence endpoint, each opened through its short-lived signed URL, with the note that a citizen photo is stored for review and is never treated as proof.
2. **Docs**
   1. `TRUECLOSE_NEXT_STEPS.md`: record the 11 answered decisions and mark the done items.
   2. `DEPLOY_STEPS.md`: step by step for Render (Engine + Agent), Supabase (auth, SQL the user runs, storage bucket) and Vercel env vars, with every secret named but never written.
3. **Left for the user**: per-ticket photos in `web/public/assets/ticket-photos/`, native-speaker review of hi/mr/kn reply text, creating the Render and Supabase accounts, running `agent/sql/schema_postgres.sql`.

## Done means
Every item above is written, nothing outside scope changed, and the final report says plainly what was not run.
