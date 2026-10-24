# Experiments (24 Oct)

Three measurements, run to replace guesses with numbers. Each section says what is **real**, what is **simulated**, and what it does **not** show. Raw outputs are in `data/experiments/`.

Status: all three sections are finished. Summary: CLIP catches the two "still broken" photos but, with its hand-set thresholds, **falsely accuses all four clean demo tickets**, so it must stay off. The cost numbers are a labelled simulation. The satellite re-run measured more locations (35 against 23) with the same conclusion: the check does not separate repaired places from random ones.

## 2. Cost versus accuracy (SIMULATION, not a real-world result)

**What ran:** `agent/experiments/cost_vs_accuracy.py 200` and `agent/experiments/cost_demo_set.py`, unchanged.

### 2a. Stub harness, 200 tickets (`data/experiments/cost_vs_accuracy.stub.txt`)

| | accuracy when decided | abstain rate | average cost per ticket |
|---|---|---|---|
| Budgeted agent | 1.0 | 0.02 | 2.47 |
| "Run every check" | 1.0 | 0.02 | 5.04 |

**Everything here is invented.** The truth label for each ticket is `hash(ticket id) % 2` (`tools.stub_truth_false`), and each stub tool reports the truth with a fixed likelihood ratio (photo 5.0 or 0.4, satellite 4.0 or 0.35, citizen 6.0 or 0.3, human 20 or 0.05; `config.VC["stub_lr"]`). A tool that always agrees with the truth gives 100% accuracy by construction. The only thing this shows is the **cost**: the agent stops early once the posterior crosses a threshold, so it spent about half the budget of running every check (2.47 against 5.04) on this made-up data. It says nothing about accuracy on real closures, and the benchmark has no per-tool outputs for the citizen or satellite checks, so a real cost-versus-accuracy number cannot be produced yet.

### 2b. Demo set, 12 tickets, real photo tool (`cost_demo_set.real_tools_no_clip.txt`, `demo_per_ticket.no_clip.txt`)

Real tools means: the Engine's real tickets and scores, the Agent's real duplicate, location and timestamp photo checks, no CLIP, no vision LLM, no Telegram contact (so no citizen reply) and no satellite (not eligible for these categories). Truth = the planted plan (clean = genuine, anything else = false). The truth and the failures were planted by us, and the photos are open-licence demo images.

| Plan | Tickets | Verdict | Posterior |
|---|---|---|---|
| clean | DEMO-000, 001, 002, g00 | cannot tell (not falsely accused) | 0.33 |
| reused photo | 003, 004 | likely not fixed | 0.97 |
| shifted GPS | 005, 006 | likely not fixed | 0.80 |
| stale timestamp | 007, 008 | likely not fixed | 0.75 |
| **still broken** | **009, 010** | **cannot tell (missed)** | 0.33 |

Summary printed by the harness: both the budgeted agent and "run everything" decide 6 of 12 (abstain rate 0.5), are right on all 6 they decide, and cost 1.0 on average, because only the photo check is available. This is an illustration on 12 planted tickets, not an accuracy result. The two "still broken" tickets are missed without a content check; section 1 tests whether CLIP closes that gap.

## 1. CLIP photo content check (real model, 12 planted tickets)

**What ran:** the Agent's existing `agent/app/clip_check.py` unchanged (no code fix was needed), with the real model OpenCLIP ViT-B-32 (laion2b_s34b_b79k) on CPU-only PyTorch 2.14, over the 12 demo tickets. Script: `data/experiments/clip_demo.py`. Results: `clip_demo.results.json`, `demo_per_ticket.with_clip.txt`, `demo_per_ticket.no_clip.txt`. The thresholds are the hand-set ones in the file (scene "still broken" at 0.65, "different place" below cosine 0.55) and were not touched.

**Cost:** about 166 s to load the model (first run, includes the weight download), about 816 MB of memory once loaded (848 MB after the run), about 0.78 s per ticket (two images plus text prompts) on this laptop's CPU. Torch and CLIP add roughly 2 GB of disk. This will not fit a small Render instance.

**What CLIP said per ticket** (scene = P(problem still present); cosine = closure photo against complaint photo):

| Ticket | Planted plan | Scene P | Cosine | CLIP flags |
|---|---|---|---|---|
| DEMO-000 | clean | 0.001 | 0.47 | before_after |
| DEMO-001 | clean | 0.000 | 0.46 | before_after |
| DEMO-002 | clean | 0.68 | 0.65 | scene |
| DEMO-g00 | clean | 0.000 | 0.39 | before_after |
| DEMO-003, 004 | reused photo | 0.001, 0.000 | 0.50, 0.45 | before_after |
| DEMO-005 | shifted GPS | 0.016 | 0.36 | before_after |
| DEMO-006 | shifted GPS | 0.054 | 0.60 | none |
| DEMO-007 | stale time | 0.009 | 0.54 | before_after |
| DEMO-008 | stale time | 0.003 | 0.57 | none |
| **DEMO-009** | **still broken** | **1.000** | 0.63 | **scene** |
| **DEMO-010** | **still broken** | **0.987** | 1.00 | **scene** |

**Verdicts with CLIP switched on** (`AGENT_USE_CLIP=1`, real tools, same 12 tickets): every ticket becomes "likely not fixed", including **all four clean tickets** (posterior 0.75 to 0.83), and the two "still broken" tickets become "likely not fixed" at 0.83. Without CLIP the same run gave "cannot tell" for the four clean tickets and for the two still-broken ones (missed).

**Reading it honestly:**
- The scene check does what it was meant to do on the two planted "still broken" photos: both are flagged. That is the gap `INTEGRATION.md` called out, now confirmed closable.
- It also flags DEMO-002, a clean ticket (P 0.68 against a 0.65 threshold): a false accusation on one of four clean tickets, one image.
- The before/after "different place" check fires on 7 of 12 tickets, including three of the four clean ones (000, 001, g00). The demo's "before" and "after" photos are different open-licence photographs chosen to look plausible, not two shots of one spot, so cosine similarity between them is low by construction. On this set that check measures nothing about the real world, and it drives the false accusations of the clean tickets.
- Twelve tickets cannot give an accuracy figure, and these thresholds were never calibrated. **No claim of photo content checking should be made from this.** Recommendation: leave `AGENT_USE_CLIP` off (it is off by default), or enable only the scene check on a labelled demo and drop the before/after check until it is tested on real before/after pairs of the same location.

## 3. Satellite validation re-run (real Sentinel-2 reads, live AWS Earth Search)

**What ran:** `python -m app.satellite.validate --n 90 --seed 7 --workers 3` from `engine/` with the repo `.venv`, the same settings as the first run (90 random Mumbai locations, real ticket date pairs, no repair claimed), after the connection-cap fix. About 59 minutes. New metrics: `data/experiments/satellite.metrics.rerun.json`; raw runs: `satellite_validation.rerun.raw.json`. The script overwrote `data/models/satellite.metrics.json`; it was **restored to the original** (a copy is in `satellite.metrics.before.json`), so the Evaluation page still shows the old numbers until you decide to adopt the new ones. The original raw run is in `satellite_validation.before.raw.json`.

| | First run | Re-run (after the fix) |
|---|---|---|
| Locations requested | 90 | 90 |
| Measured | 23 | **35** |
| Abstained | 67 (74.4%) | 55 (61.1%) |
| Abstained: cloud in every nearby scene | 44 | 41 (+1 cloud or no data in one scene) |
| Abstained: read errors | 23 (RasterioIOError) | **13** (11 RasterioIOError, 2 connection aborted) |
| Median seconds per check | 18.9 | 32.1 |
| Placebo detection rate (expected 10%) | 13.0% (95% CI 2.8 to 33.6%) | **14.3% (95% CI 4.8 to 30.3%)** |
| Mean percentile (expected 0.5) / KS test against uniform | 0.564 / p = 0.40 | 0.570 / p = 0.074 |
| Sigma floor deciding the scale | 7.6% | 5.0% |

Power (detection rate against an injected change, in control sigmas), first run then re-run: 0: 13% then 14%; 0.5: 17% then 14%; 1: 24% then 23%; 1.5: 40% then 37%; 2: 65% then 66%; 3: 95% then 90%; 4: 100% then 95%; 6: 100% then 100%. (115 and 175 injected trials.)

**Reading it honestly:**
- The fix helped but did not remove the read errors: 13 of 90 (14%) against 23 of 90 (26%). The remaining errors are the same Rasterio read failure plus two dropped connections, so the load problem is reduced, not gone.
- Cloud is still the main limit: 41 to 44 of 90 locations are hidden in every nearby scene, so about half the time the check abstains whatever we do.
- With 35 measured locations the conclusions are unchanged and a little better supported: at random places with no repair claimed, the check still reports an unusual change 14% of the time (expected 10%, interval 5 to 30%), so it does **not** separate repaired places from random ones. The KS p-value dropped to 0.07, a weak hint that percentiles are not perfectly uniform; do not over-read it at this sample size.
- This is still placebo and injected-change validation, not validation against real repairs, which do not exist. The likelihood ratios (0.45 and 1.25) remain unvalidated.
- Decision for the project owner: adopt the re-run numbers on the Evaluation page (copy `satellite.metrics.rerun.json` over `data/models/satellite.metrics.json`) or keep the first run. Nothing was changed in `data/models/`.

## Files

`EXPERIMENTS.md`; `data/experiments/`: `clip_demo.py`, `clip_demo.results.json`, `demo_per_ticket.py`, `demo_per_ticket.no_clip.txt`, `demo_per_ticket.with_clip.txt`, `cost_vs_accuracy.stub.txt`, `cost_demo_set.real_tools_no_clip.txt`, `satellite.metrics.before.json`, `satellite.metrics.rerun.json`, `satellite_validation.before.raw.json`, `satellite_validation.rerun.raw.json`, `satellite_rerun.stdout.log`.
