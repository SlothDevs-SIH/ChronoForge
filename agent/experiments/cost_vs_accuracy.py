"""Cost-vs-accuracy: adaptive agent vs "run every eligible check". Run from agent/:

    .venv/Scripts/python -m experiments.cost_vs_accuracy [N]

IMPORTANT: this uses the STUB tools and the stub ground truth, so the numbers only prove the harness works.
Once Soham's benchmark (data/benchmark_v1.parquet) and the real tools exist, point TICKETS/truth at it and
report those numbers on the eval page instead.
"""
import sys

from app import agent, config, db, fusion, tools
from app.models import Evidence


def run_everything(tid: str):
    score, _ = tools.get_score(tid)
    ev: list[Evidence] = [tools.check_photo(tid), tools.ask_citizen(tid)]
    if score.satellite_eligible:
        ev.append(tools.check_satellite(tid, True))
    post = fusion.fuse(score.p_false_closure, ev)
    return fusion.state_for(post), sum(e.cost for e in ev)


def correct(state: str, truly_false: bool) -> bool | None:
    if state == "cannot_tell":
        return None   # abstention: counted separately
    return (state == "likely_not_fixed") == truly_false


def summarise(rows):
    n = len(rows)
    decided = [c for c, _ in rows if c is not None]
    return {"tickets": n, "accuracy_when_decided": round(sum(decided) / max(len(decided), 1), 3),
            "abstain_rate": round((n - len(decided)) / n, 3), "avg_cost": round(sum(c for _, c in rows) / n, 2)}


def main(n: int = 200):
    db.reset(":memory:")
    config.USE_STUBS, config.STEP_DELAY = True, 0
    adaptive, everything = [], []
    for i in range(n):
        tid = f"EXP-{i}"
        truth = tools.stub_truth_false(tid)
        run_id = agent.start_run(tid)
        v = agent.execute(run_id, delay=0)
        adaptive.append((correct(v.state, truth), agent.RUNS[run_id].cost_spent))
        state, cost = run_everything(tid)
        everything.append((correct(state, truth), cost))
    print("STUB DATA - harness check only")
    print("adaptive agent  :", summarise(adaptive))
    print("run everything  :", summarise(everything))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
