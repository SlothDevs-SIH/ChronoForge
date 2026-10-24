"""Cost-versus-accuracy on the labelled demo set with the REAL tools (needs the Engine running with `ingest demo`):

    AGENT_USE_STUBS=0 AGENT_USE_VISION_LLM=1 .venv/Scripts/python -m experiments.cost_demo_set

12 tickets, so this is an illustration of the harness on real verifiers, not a result. Truth = the planted plan
(clean = genuine closure, anything else = false). "Run everything" = photo + citizen + satellite when eligible.
"""
import json
import os
import sys

os.environ["PHOTO_INDEX"] = os.path.join(os.environ.get("TEMP", "/tmp"), "cost_demo_index.json")
if os.path.exists(os.environ["PHOTO_INDEX"]):
    os.remove(os.environ["PHOTO_INDEX"])
os.environ.setdefault("LLM_PROVIDERS", "")
os.environ["AGENT_DB"] = ":memory:"
os.environ["STEP_DELAY"] = "0"

from app import agent, config, fusion, tools  # noqa: E402
from experiments.cost_vs_accuracy import correct, summarise  # noqa: E402


def main():
    config.USE_STUBS = False
    plans = {m["ticket_id"]: m["planted_failure"] for m in json.load(open(config.REPO_ROOT / "demo/photos/manifest.json"))}
    adaptive, everything = [], []
    for tid, bad in plans.items():
        run_id = agent.start_run(tid)
        v = agent.execute(run_id, delay=0)
        adaptive.append((correct(v.state, bad), agent.RUNS[run_id].cost_spent))
        score, _ = tools.get_score(tid)
        ev = [tools.check_photo(tid), tools.ask_citizen(tid)]
        if score.satellite_eligible:
            ev.append(tools.check_satellite(tid, True))
        post = fusion.fuse(score.p_false_closure, ev)
        everything.append((correct(fusion.state_for(post), bad), sum(e.cost for e in ev)))
    print("DEMO SET, 12 tickets, real tools; an illustration, not a result")
    print("adaptive agent :", summarise(adaptive))
    print("run everything :", summarise(everything))


if __name__ == "__main__":
    sys.exit(main())
