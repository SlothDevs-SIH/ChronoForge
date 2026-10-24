# Run the Engine and Agent on Hugging Face Spaces

**Docker Spaces on free hardware now require a Hugging Face PRO subscription** (checked 25 Oct). With PRO: 2 vCPU and 16 GB of memory per Space. Each Space is a Docker Space that holds only a `Dockerfile` and a
`README.md`; the code is pulled from the public GitHub repo (branch `main`) when the Space builds. You create the
account and the Spaces; nothing here is run for you.

Limits to know: a free Space goes to sleep after about 48 hours without a request and wakes on the next one (about a
minute). It has no persistent disk, so the Engine downloads the warehouse again after every restart, and the Engine's
`status_overrides.json` (the simulated municipal reopen) resets. Everything that matters (users, approvals, audit,
runs) lives in Supabase Postgres, which the Agent uses.

I have not built these images yet (no Docker on the machine that wrote them). Expect to fix a small thing on the first build.

Replace `<hf-user>` below with your Hugging Face username (lowercase). A Space named `trueclose-engine` is served at
`https://<hf-user>-trueclose-engine.hf.space`.

## 1. Account
Sign up at huggingface.co and confirm your email.

## 2. Create the Engine Space
1. Profile menu > **New Space**.
2. Space name `trueclose-engine`. License: any. SDK: **Docker**, template **Blank**. Hardware: **CPU basic, free**. Visibility: **Public**
   (the site calls it from the browser; the code in it holds no secrets).
3. **Create Space**.
4. Open the **Files** tab > **Add file > Upload files**. Upload `deploy/huggingface/engine/Dockerfile` and
   `deploy/huggingface/engine/README.md` from this repository (the README replaces the default one). Commit.
5. **Settings > Variables and secrets.** Variables are readable by anyone on a public Space, so only put non-sensitive values there.

| Name | Kind | Value |
|---|---|---|
| `AUTH_REQUIRED` | Variable | `1` |
| `SUPABASE_URL` | Variable | `https://lluurewdubfdirgwkeez.supabase.co` (no `/rest/v1/`, no trailing `/`) |
| `AGENT_URL` | Variable | `https://<hf-user>-trueclose-agent.hf.space` |
| `CORS_ORIGINS` | Variable | `https://trueclose-neon.vercel.app` |
| `ENGINE_SERVICE_TOKEN` | **Secret** | the same long random string you give the Agent |
| `WAREHOUSE_URL` | **Secret** | the signed link to `warehouse.tar.gz` in the Supabase `warehouse` bucket |

6. The Space builds on its own (the **Logs** tab shows it). When it says **Running**, open
   `https://<hf-user>-trueclose-engine.hf.space/ready`. You want `"ready":true` and `"mode":"warehouse"`. The first start downloads the
   warehouse, so give it a minute or two.

## 3. Create the Agent Space
Same steps with name `trueclose-agent`, uploading `deploy/huggingface/agent/Dockerfile` and `deploy/huggingface/agent/README.md`.

| Name | Kind | Value |
|---|---|---|
| `AUTH_REQUIRED` | Variable | `1` |
| `SUPABASE_URL` | Variable | `https://lluurewdubfdirgwkeez.supabase.co` |
| `ENGINE_URL` | Variable | `https://<hf-user>-trueclose-engine.hf.space` |
| `AGENT_USE_STUBS` | Variable | `0` |
| `PUBLIC_DEMO_RUNS` | Variable | `1` |
| `CORS_ORIGINS` | Variable | `https://trueclose-neon.vercel.app` |
| `STORAGE_BACKEND` | Variable | `supabase` |
| `SUPABASE_BUCKET` | Variable | `evidence` |
| `DATABASE_URL` | **Secret** | the Supabase **Session pooler** string, with your database password |
| `SUPABASE_SERVICE_KEY` | **Secret** | the Supabase service_role key |
| `ADMIN_EMAILS` | **Secret** | the four team emails, comma separated |
| `ENGINE_SERVICE_TOKEN` | **Secret** | the same string as the Engine |
| `REPLY_LINK_SECRET` | **Secret** | another long random string |

Open `https://<hf-user>-trueclose-agent.hf.space/ready`: you want `"ok":true` and `"database":"postgres"`.

(`TRUST_PROXY` is already set to `1` in the image.)

## 4. Point the site at them
Send the two `.hf.space` addresses. The site then needs `VITE_ENGINE_URL` and `VITE_AGENT_URL` set to them in Vercel, and the
`/api/...` proxy rewrites removed from `web/vercel.json`.

## 5. Switch the Render services off
Once the site works against the Spaces, suspend both Render services (Settings > Suspend) so nothing runs in two places.

## Updating
Push to `main` on GitHub, then in each Space: **Settings > Factory rebuild**. A normal restart reuses the old build.

## If something fails
- Build fails on `git clone`: the GitHub repo must stay public.
- `/ready` says no warehouse: the `WAREHOUSE_URL` link expired or is the dashboard page, not the signed download link.
- Agent `/ready` says database unreachable: `DATABASE_URL` must be the **pooler** string; the direct one is IPv6-only.
- A Space shows **Sleeping**: open its address and wait a minute.
