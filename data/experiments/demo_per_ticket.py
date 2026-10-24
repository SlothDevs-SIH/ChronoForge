"""Per-ticket view of the demo-set run (real tools, no CLIP). Run from agent/ with the Agent's venv:

    ENGINE_URL=http://127.0.0.1:8011 AGENT_USE_STUBS=0 python ../data/experiments/demo_per_ticket.py [--clip]

Prints one line per demo ticket: planted plan, verdict state, posterior, cost, and the checks that were flagged.
Truth = the planted plan (clean = genuine closure, anything else = false closure). 12 tickets: an illustration only.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["PHOTO_INDEX"] = os.path.join(os.environ.get("TEMP", "/tmp"), "exp_demo_index.json")
if os.path.exists(os.environ["PHOTO_INDEX"]):
    os.remove(os.environ["PHOTO_INDEX"])
os.environ.setdefault("LLM_PROVIDERS", "")
os.environ["AGENT_DB"] = ":memory:"
os.environ["STEP_DELAY"] = "0"
if "--clip" in sys.argv:
    os.environ["AGENT_USE_CLIP"] = "1"

from app import agent, config  # noqa: E402

config.USE_STUBS = False
manifest = json.load(open(config.REPO_ROOT / "demo/photos/manifest.json"))
rows = []
for m in manifest:
    run_id = agent.start_run(m["ticket_id"])
    v = agent.execute(run_id, delay=0)
    run = agent.RUNS[run_id]
    rows.append({"ticket": m["ticket_id"], "plan": m["plan"], "planted_failure": m["planted_failure"], "state": v.state,
                 "prior": round(v.prior, 3), "posterior": round(v.posterior, 3), "cost": run.cost_spent,
                 "explanation": v.explanation[:160]})
    print(f'{m["ticket_id"]:9} {m["plan"]:12} fail={str(m["planted_failure"]):5} -> {v.state:17} post={v.posterior:.2f} cost={run.cost_spent}')
print(json.dumps(rows, indent=1))
