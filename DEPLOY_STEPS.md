# Deploy steps (Render, Supabase, Vercel)

You do the account and database steps; nothing here is run for you. Variable names come from `contract/AUTH_AND_DEPLOY.md`, `agent/.env.example` and `engine/.env.example`. Never paste a real secret into git or into chat.

Not yet verified against real services: Postgres mode, Supabase sign-in and storage, token checks against Supabase keys, the Docker builds. Expect to fix small things on the first deploy.

## 1. Supabase (sign-in, database, photo storage)

1. Create a project at supabase.com. Note the project URL (`https://<ref>.supabase.co`).
2. Authentication > Providers: keep Email on. Leave Google and GitHub off. Turn "Confirm email" on, because admin sign-up depends on a confirmed email.
3. Authentication > URL Configuration: set Site URL to `https://trueclose-neon.vercel.app` and add `http://localhost:5174` as a redirect URL.
4. SQL Editor: open `agent/sql/schema_postgres.sql`, read it, and run it once. The Agent never creates tables itself.
5. Storage: create a bucket named `evidence` and make it **private**.
6. Project Settings > API: copy the URL, the anon key (goes to the browser) and the service_role key (server only, goes to the Agent). Under Database, copy the pooled connection string for `DATABASE_URL`.

## 2. Render: Agent

New > Web Service > from the GitHub repo, branch `feature/auth-and-deploy`, leave Root Directory empty (the repo root is the Docker build context), runtime Docker, Dockerfile Path `agent/Dockerfile`. Environment:

| Variable | Value |
|---|---|
| `AUTH_REQUIRED` | `1` |
| `DATABASE_URL` | Supabase pooled connection string |
| `SUPABASE_URL` | your project URL |
| `ADMIN_EMAILS` | the four team emails, comma separated |
| `ENGINE_URL` | the Engine's Render address (step 3) |
| `AGENT_USE_STUBS` | `0` |
| `ENGINE_SERVICE_TOKEN` | a long random string (same on the Engine) |
| `REPLY_LINK_SECRET` | another long random string |
| `CORS_ORIGINS` | `https://trueclose-neon.vercel.app` |
| `PUBLIC_DEMO_RUNS` | `1` (lets the public System status page run `DEMO-*` only) |
| `TRUST_PROXY` | `1` |
| `STORAGE_BACKEND` | `supabase` |
| `SUPABASE_SERVICE_KEY` | the service_role key |
| `SUPABASE_BUCKET` | `evidence` |

Add a persistent disk (for `PHOTO_INDEX`) if you want duplicate-photo memory to survive restarts.

## 3. Render: Engine

New > Web Service, same repo and branch, Root Directory empty, runtime Docker, Dockerfile Path `engine/Dockerfile`. Add a persistent disk mounted at `/var/data`. Environment:

| Variable | Value |
|---|---|
| `AUTH_REQUIRED` | `1` |
| `SUPABASE_URL` | your project URL |
| `AGENT_URL` | the Agent's Render address |
| `ENGINE_SERVICE_TOKEN` | the same string as the Agent |
| `CORS_ORIGINS` | `https://trueclose-neon.vercel.app` |
| `WAREHOUSE_URL` | a private link to `warehouse.tar.gz` (the Parquet files, about 28 MB) |

The warehouse is not in git. Pack `data/warehouse` into a `.tar.gz`, upload it somewhere private (a Supabase Storage signed link works), and put that link in `WAREHOUSE_URL`. The Engine downloads it on first start when the disk is empty.

Then set `ENGINE_URL` on the Agent and `AGENT_URL` on the Engine to each other's addresses and redeploy both.

## 4. Vercel (web)

In the `trueclose` project, Settings > Environment Variables (Production):

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | your project URL |
| `VITE_SUPABASE_ANON_KEY` | the anon key |
| `VITE_ENGINE_URL` | the Engine's Render address |
| `VITE_AGENT_URL` | the Agent's Render address |

Do not set `VITE_AUTH_DISABLED`. Redeploy after saving.

## 5. First sign-in

1. Open the site, register with an email listed in `ADMIN_EMAILS`, confirm the email, sign in. You land as admin.
2. Officers register through "Official sign-in" and wait as pending. Approve them in Admin.
3. Citizens register on their own. In Admin, link a ticket id to each citizen so it appears under My tickets.

## Still needed from you
- Per-ticket photos: files in `web/public/assets/ticket-photos/` plus the mapping in `index.json`.
- A native speaker to check the Hindi, Marathi and Kannada reply text.
- Whether to adopt the re-run satellite numbers in `data/experiments/satellite.metrics.rerun.json`.
