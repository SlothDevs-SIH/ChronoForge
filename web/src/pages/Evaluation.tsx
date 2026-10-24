import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { ErrorState, Skeleton } from "../components/States";
import PublicNav, { PublicFooter } from "../components/PublicNav";

/* The Engine's results file is a large nested document; it is read loosely and every figure shown comes from it. */
/* eslint-disable @typescript-eslint/no-explicit-any */
const pct = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`;
const ci = (c?: number[]) => (c ? `${c[0].toFixed(2)} to ${c[1].toFixed(2)}` : "");

function Synthetic() {
  return <span className="tag tag-simulated"><b>Synthetic injection</b></span>;
}

export default function Evaluation() {
  const { data, isPending, error, refetch } = useQuery({ queryKey: ["eval"], queryFn: api.evalResults, retry: false });
  const e: any = data;
  const bl = e?.scorers?.["blr-reopen-v1"], mu = e?.scorers?.["mum-flags-v1"], sy = e?.scorers?.["syn-truth-v1"];
  const bench = e?.verifiers?.benchmark_v1, sat = e?.verifiers?.satellite;
  const shipped = bl?.results_on_test?.["SHIPPED(lgbm)"], catBase = bl?.results_on_test?.baseline_category_rate;
  const flag = mu?.flag_effects?.citizen_image_only;
  const symptoms: [string, any][] = bench ? Object.entries(bench.results.per_symptom) : [];
  const ready = e && bl && mu && sy && bench && sat && shipped && flag;

  return (
    <div className="pub-page">
      <PublicNav />
      <main className="pub-main">
        <header className="pub-head">
          <h1>Evaluation</h1>
          <p>What we measured, on which data, and what it does not show. We claim no real-world false-closure rate. Every figure below is read from the Engine's stored results.</p>
        </header>
        {isPending && <Skeleton rows={6} label="Loading results" />}
        {error && <ErrorState error={error} onRetry={() => void refetch()} title="We couldn't load the results" />}
        {e && !ready && <p className="muted">The Engine returned results in an unexpected shape, so nothing is shown rather than guessing.</p>}
        {ready && <>
          <section className="panel" aria-labelledby="sc">
            <div className="panel-head"><div><h2 id="sc">Closure scorers</h2><p>How well each scorer orders closed tickets, tested on later months than it trained on.</p></div></div>
            <div className="eval-grid">
              <article>
                <h3>Bengaluru <span className="tag tag-real"><b>Real</b> proxy label</span></h3>
                <p className="eval-big">{shipped.auroc.toFixed(2)}<span> test AUROC</span></p>
                <p className="fine">95% interval {ci(shipped.auroc_ci95)}. The top 10% of scores hold {pct(shipped.lift_top10pct.recall)} of reopened tickets, about {shipped.lift_top10pct.lift.toFixed(1)} times chance. Category alone scores {catBase.auroc.toFixed(2)}.</p>
                <p className="fine">A rank, not a probability. The label is "the citizen reopened the closure", a lower bound on false closure.</p>
              </article>
              <article>
                <h3>Mumbai <span className="tag tag-real"><b>Real</b> proxy label</span></h3>
                <p className="eval-big">×{flag.all_months.odds_ratio_density_adjusted.toFixed(1)}<span> repeat-complaint odds</span></p>
                <p className="fine">For closures with only the citizen's own photo ({flag.all_months.n_flagged} tickets), 95% interval {ci(flag.all_months.odds_ratio_ci95)}; held-out months {ci(flag.held_out_aug_onward.odds_ratio_ci95)}. No trained model ships for Mumbai because crowding explains most of the signal.</p>
              </article>
              <article>
                <h3>Pune and sandbox <Synthetic /></h3>
                <p className="eval-big">{String(sy.validation_auroc).match(/'lgbm': ([0-9.]+)/)?.[1] ?? "n/a"}<span> validation AUROC</span></p>
                <p className="fine">High because we injected the failures. It shows the model recovers the failure modes we planted, nothing more.</p>
              </article>
            </div>
          </section>

          <section className="panel" aria-labelledby="bm">
            <div className="panel-head"><div><h2 id="bm">Metadata checks on injected failures</h2><p>{bench.base}. {pct(bench.failure_rate_injected)} of tickets were turned into failures with a known symptom.</p></div><Synthetic /></div>
            <table className="eval-table">
              <caption className="sr-only">Recall and false alarms by injected symptom</caption>
              <thead><tr><th scope="col">Injected symptom</th><th scope="col" className="num">Injected</th><th scope="col">Caught</th><th scope="col" className="num">False alarms on clean tickets</th></tr></thead>
              <tbody>{symptoms.map(([name, r]) => (
                <tr key={name}><th scope="row">{name.replace(/_/g, " ")}</th><td className="num">{r.injected}</td>
                  <td><span className="meter"><i style={{ width: pct(r.recall) }} /></span> <b>{pct(r.recall)}</b> <span className="fine">({ci(r.recall_ci95)})</span></td>
                  <td className="num">{r.false_alarms_on_clean} ({pct(r.false_alarm_rate_on_clean, 1)})</td></tr>
              ))}</tbody>
            </table>
            <p className="eval-callout"><b>{pct(bench.results.failures_with_no_symptom.share_of_failures)} of failures leave no metadata symptom.</b> Only independent evidence (satellite, photo content, citizen, human) can catch them, and that is why the agent exists.</p>
            <p className="fine">Injected symptoms are caught by construction, so high recall here is not a real-world result. Batch closing is not used as a signal: {pct(bench.results.natural_flag_rates_real_data.same_officer_same_minute_clusters.share_of_real_tickets)} of real Mumbai tickets sit in same-officer, same-minute clusters, often kilometres apart.</p>
          </section>

          <section className="panel" aria-labelledby="st">
            <div className="panel-head"><div><h2 id="st">Satellite check</h2><p>There are no real repair labels, so this shows how the check behaves, not that it finds real repairs.</p></div><span className="tag tag-real"><b>Real</b> Sentinel-2</span></div>
            <p className="eval-line"><b>{sat.n_measured}</b> of {sat.n_requested} locations could be measured; <b>{sat.n_abstained}</b> abstained ({pct(sat.abstention_rate)}), mostly because of cloud or missing scenes.</p>
            <p className="eval-line">At random places where no repair was claimed it still reported a change {pct(sat.placebo.observed_detection_rate)} of the time (expected {pct(sat.placebo.expected_detection_rate)}; 95% interval {pct(sat.placebo.observed_ci95[0])} to {pct(sat.placebo.observed_ci95[1])}). So it does not separate repaired places from random ones.</p>
            <table className="eval-table"><caption className="sr-only">Detection rate against injected change</caption>
              <thead><tr><th scope="col">Injected change (control sigmas)</th><th scope="col">Detection rate</th></tr></thead>
              <tbody>{sat.power.map((r: any) => <tr key={r.injected_change_in_control_sigmas}><th scope="row">{r.injected_change_in_control_sigmas}</th><td><span className="meter"><i style={{ width: pct(r.detection_rate) }} /></span> <b>{pct(r.detection_rate)}</b></td></tr>)}</tbody></table>
            <ul className="eval-limits">{sat.limits_of_this_validation.map((l: string) => <li key={l}>{l}</li>)}</ul>
          </section>

          <section className="panel" aria-labelledby="pd">
            <div className="panel-head"><div><h2 id="pd">Not measured yet</h2></div><span className="tag tag-missing"><b>Not built</b></span></div>
            <ul className="eval-limits">{(e.pending as string[]).map((p) => <li key={p}>{p}</li>)}<li>Likelihood ratios in the Agent are hand-set assumptions, not calibrated on real closures.</li><li>Human override rate needs real approval decisions, which only exist in the demo.</li></ul>
          </section>
        </>}
      </main>
      <PublicFooter current="/evaluation" />
    </div>
  );
}
