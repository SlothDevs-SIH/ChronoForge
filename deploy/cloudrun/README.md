# Run the Engine and Agent on Google Cloud Run

Cloud Run runs the same Docker images as before (`engine/Dockerfile`, `agent/Dockerfile`), gives each service its own
`https://...run.app` address, and scales to zero when idle. There is no shared `onrender.com` edge, and 2 GB of memory per
service is a setting, not a plan. You need a Google Cloud account with **billing enabled** (a card; new accounts get a free
trial credit, and Cloud Run has a free monthly allowance, but charges can still occur). Set a budget alert in step 2.

Not yet built or run: these files are untested. Expect to fix a small thing on the first deploy.

Replace `PROJECT_ID` with your project id. The region `asia-south1` is Mumbai. Run every command from the repository root,
in PowerShell. Commands that start with `gcloud` need the Google Cloud CLI.

## 1. Install the CLI and log in (you do this)
1. Install the Google Cloud CLI for Windows: https://cloud.google.com/sdk/docs/install (run the installer, then open a new PowerShell).
2. `gcloud auth login` and sign in in the browser that opens.
3. In the Cloud Console create a project (for example `trueclose`), note its **Project ID**, and link a billing account to it.
4. `gcloud config set project PROJECT_ID`

## 2. One-time setup
```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create trueclose --repository-format=docker --location=asia-south1
```
In the Console, Billing > Budgets & alerts: create a small budget with an email alert.

## 3. Fill in the two environment files
Copy `deploy/cloudrun/engine.env.example.yaml` to `engine.env.yaml` and `agent.env.example.yaml` to `agent.env.yaml` (same folder)
and fill in the values. The filled-in copies are git-ignored; never commit them. Use the **same** `ENGINE_SERVICE_TOKEN` in both.
Leave `AGENT_URL` and `ENGINE_URL` for step 5.

## 4. Build and deploy the Agent
```powershell
$AI = "asia-south1-docker.pkg.dev/PROJECT_ID/trueclose/agent"
gcloud builds submit --config deploy/cloudrun/cloudbuild-agent.yaml --substitutions "_IMAGE=$AI" .
gcloud run deploy trueclose-agent --image $AI --region asia-south1 --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 900 --max-instances 3 --env-vars-file deploy/cloudrun/agent.env.yaml
```
The deploy prints the service URL (`https://trueclose-agent-....run.app`). Check `<url>/ready`: `"ok":true` and `"database":"postgres"`.

## 5. Build and deploy the Engine
Put the Agent's URL into `engine.env.yaml` as `AGENT_URL`, then:
```powershell
$EI = "asia-south1-docker.pkg.dev/PROJECT_ID/trueclose/engine"
gcloud builds submit --config deploy/cloudrun/cloudbuild-engine.yaml --substitutions "_IMAGE=$EI" .
gcloud run deploy trueclose-engine --image $EI --region asia-south1 --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 300 --max-instances 3 --env-vars-file deploy/cloudrun/engine.env.yaml
```
Check `<engine url>/ready`: `"ready":true`, `"mode":"warehouse"`. The first request after a quiet period downloads the warehouse
again (about a minute), because the instance starts empty.

Now tell the Agent where the Engine is:
```powershell
gcloud run services update trueclose-agent --region asia-south1 --update-env-vars "ENGINE_URL=https://trueclose-engine-....run.app"
```

## 6. Point the site at them
Send the two `run.app` addresses. The site then needs `VITE_ENGINE_URL` and `VITE_AGENT_URL` set to them in Vercel and the
`/api/...` proxy rewrites removed from `web/vercel.json`. Then suspend the Render services.

## Notes
- `--allow-unauthenticated` only opens the network door. Every data route still requires a signed-in Supabase user.
- Scale to zero means the first request after idle is slow. For a live demo, add `--min-instances 1` to both services (it costs money).
- The Agent runs verification work in the background after a request returns. Cloud Run slows the CPU of an instance with no
  open request, so a run you stop watching can stall. Keep the ticket page open, or add `--no-cpu-throttling` to the Agent (billed while it is up).
- The Engine's `status_overrides.json` (the simulated municipal reopen) resets whenever an instance restarts. Users, approvals and
  the audit log are in Supabase and are safe.
- Update a service after a code change: repeat its `builds submit` and `run deploy` commands.
