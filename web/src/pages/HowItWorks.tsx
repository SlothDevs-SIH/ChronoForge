import { useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Icon, { type IconName } from "../components/Icon";
import PublicNav from "../components/PublicNav";

type Kind = "real" | "simulated" | "missing";
interface Step { id: string; title: string; icon: IconName; summary: string; points: string[]; status: { kind: Kind; text: string }[] }

// Every figure here is taken from the repository's measured results (README.md, INTEGRATION.md, engine/app/benchmark).
const STEPS: Step[] = [
  { id: "marked", title: "A complaint is marked resolved", icon: "list",
    summary: "TrueClose starts from tickets a city has already closed. It does not take the closure on trust.",
    points: ["Bengaluru and Mumbai tickets are real public records. Pune and a sandbox city are synthetic.", "Batch closing is common in Mumbai (29% of closures), so the closing pattern alone is not treated as a warning."],
    status: [{ kind: "real", text: "Bengaluru and Mumbai records" }, { kind: "simulated", text: "Pune, sandbox and demo cities" }] },
  { id: "risk", title: "Risk assessment", icon: "gauge",
    summary: "A scorer orders the queue so limited checking effort goes to the closures most likely to be wrong.",
    points: ["Bengaluru: a risk rank with a test AUROC of about 0.60 to 0.64. That is a weak signal that orders a queue, not a probability.", "Mumbai: a flag for closures that rest on the citizen's image alone. No percentage chance is shown.", "Only the synthetic cities have a calibrated probability, and they are labelled as synthetic."],
    status: [{ kind: "real", text: "Rank and flags on real data" }, { kind: "missing", text: "No calibrated probability for real cities" }] },
  { id: "evidence", title: "Evidence collection", icon: "photo",
    summary: "The agent chooses checks within a budget of 10. Cheap checks come first and a person is the most expensive.",
    points: ["Closure photo, cost 1: looks for a reused image, a shifted location and a stale timestamp.", "Citizen reply, cost 2: asked on Telegram. A reply is evidence, not automatic truth.", "Satellite, cost 3: before and after Sentinel-2 imagery, only for problems large enough to see from orbit (558 of 77,338 Mumbai tickets). Cloud makes it abstain.", "Human spot check, cost 10."],
    status: [{ kind: "real", text: "Sentinel-2 imagery" }, { kind: "simulated", text: "Photo checks run on the demo photo set" }, { kind: "missing", text: "WhatsApp channel" }] },
  { id: "evaluation", title: "Evaluation", icon: "scale",
    summary: "Each piece of evidence multiplies the odds of a false closure by a likelihood ratio. Try it below.",
    points: ["Evidence that points to a fix lowers the odds. Evidence against raises them.", "A check that cannot tell contributes a ratio of 1 and changes nothing."],
    status: [{ kind: "real", text: "Fusion rule is implemented and tested" }] },
  { id: "verdict", title: "Verdict", icon: "check",
    summary: "The posterior maps to one of three states. Most real tickets end as cannot tell, and the product says so.",
    points: ["At 75% or higher: likely not fixed. At 25% or lower: verified fixed. Anything between: cannot tell.", "Outcome verification is weak on real tickets because few can be checked from orbit or by photo."],
    status: [{ kind: "real", text: "Thresholds are set in the Agent" }] },
  { id: "human", title: "Human review", icon: "person",
    summary: "The agent only recommends. Reopening or escalating needs a person to approve it in the approval queue.",
    points: ["The verdict and the evidence behind it are stored with the decision in an audit chain.", "Approving calls the municipal endpoint. In this build that endpoint is simulated."],
    status: [{ kind: "real", text: "Approval queue and audit chain" }, { kind: "simulated", text: "Municipal endpoint" }] },
];

const KIND_LABEL: Record<Kind, string> = { real: "Real", simulated: "Simulated", missing: "Not built" };

// Likelihood ratios used by the Agent (agent/app/evidence). They multiply the odds that the closure was false.
const PHOTO = [{ label: "No photo problem found", lr: 0.5 }, { label: "Photo is a duplicate", lr: 8 }, { label: "Photo location is off", lr: 4 }, { label: "Photo timestamp is stale", lr: 3 }];
const CITIZEN = [{ label: "No reply yet", lr: 1.2 }, { label: "Citizen says yes, fixed", lr: 0.3 }, { label: "Citizen says partly fixed", lr: 2 }, { label: "Citizen says no, not fixed", lr: 6 }];
const SATELLITE = [{ label: "Not checked", lr: 1 }, { label: "Change seen at the site", lr: 0.45 }, { label: "No change seen at the site", lr: 1.25 }];

function verdictFor(p: number) {
  if (p >= 0.75) return { text: "Likely not fixed", tone: "danger" };
  if (p <= 0.25) return { text: "Verified fixed", tone: "success" };
  return { text: "Cannot tell", tone: "warning" };
}

function FusionExample() {
  const [prior, setPrior] = useState(30);
  const [photo, setPhoto] = useState(0);
  const [citizen, setCitizen] = useState(0);
  const [satellite, setSatellite] = useState(0);
  const ids = { prior: useId(), photo: useId(), citizen: useId(), sat: useId() };
  const { posterior, rows } = useMemo(() => {
    const picks = [{ name: "Closure photo", ...PHOTO[photo] }, { name: "Citizen reply", ...CITIZEN[citizen] }, { name: "Satellite", ...SATELLITE[satellite] }];
    const p0 = prior / 100;
    const odds = picks.reduce((o, x) => o * x.lr, p0 / (1 - p0));
    return { posterior: odds / (1 + odds), rows: picks };
  }, [prior, photo, citizen, satellite]);
  const v = verdictFor(posterior);

  return (
    <section className="panel fusion" aria-labelledby="fusion-title">
      <div className="panel-head">
        <div><h2 id="fusion-title">Try the evaluation</h2><p>An example you can change. The starting risk is a made-up value, not a real ticket.</p></div>
        <span className="tag tag-simulated">Example</span>
      </div>
      <div className="fusion-grid">
        <div className="fusion-controls">
          <label htmlFor={ids.prior}>Starting risk of a false closure: <b>{prior}%</b></label>
          <input id={ids.prior} type="range" min={5} max={90} step={5} value={prior} onChange={(e) => setPrior(Number(e.target.value))} />
          <label htmlFor={ids.photo}>Closure photo</label>
          <select id={ids.photo} value={photo} onChange={(e) => setPhoto(Number(e.target.value))}>{PHOTO.map((o, i) => <option key={o.label} value={i}>{o.label}</option>)}</select>
          <label htmlFor={ids.citizen}>Citizen reply</label>
          <select id={ids.citizen} value={citizen} onChange={(e) => setCitizen(Number(e.target.value))}>{CITIZEN.map((o, i) => <option key={o.label} value={i}>{o.label}</option>)}</select>
          <label htmlFor={ids.sat}>Satellite check</label>
          <select id={ids.sat} value={satellite} onChange={(e) => setSatellite(Number(e.target.value))}>{SATELLITE.map((o, i) => <option key={o.label} value={i}>{o.label}</option>)}</select>
        </div>
        <div className="fusion-result" aria-live="polite">
          <table>
            <caption className="sr-only">Likelihood ratio contributed by each check</caption>
            <thead><tr><th scope="col">Check</th><th scope="col" className="num">Odds multiplier</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.name}><th scope="row">{r.name}</th><td className="num">×{r.lr}</td></tr>)}</tbody>
          </table>
          <div className="fusion-posterior">
            <span>Chance the closure was false after the evidence</span>
            <strong>{Math.round(posterior * 100)}%</strong>
            <span className={`verdict verdict-${v.tone}`}>{v.text}</span>
          </div>
          <p className="fine">A human still approves any reopen. Ratios are the Agent's configured values; they are priors, not measured on real closures.</p>
        </div>
      </div>
    </section>
  );
}

export default function HowItWorks() {
  const [active, setActive] = useState(0);
  const step = STEPS[active];
  const cities = useQuery({ queryKey: ["cities"], queryFn: api.cities, retry: false });
  const total = cities.data?.reduce((n, c) => n + c.tickets, 0);

  return (
    <div className="pub-page">
      <PublicNav />
      <main className="pub-main">
        <header className="pub-head">
          <h1>How TrueClose checks a closed complaint</h1>
          <p>Six steps from "resolved" to a decision a person can defend. Each step says what is real, what is simulated and what is not built yet.</p>
        </header>

        <div className="steps">
          <div className="step-list" role="tablist" aria-label="Verification steps" aria-orientation="vertical">
            {STEPS.map((s, i) => (
              <button key={s.id} type="button" role="tab" id={`tab-${s.id}`} aria-selected={i === active} aria-controls="step-panel" tabIndex={i === active ? 0 : -1}
                className={`step-tab ${i === active ? "is-active" : ""}`} onClick={() => setActive(i)}
                onKeyDown={(e) => {
                  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
                  e.preventDefault();
                  const n = (i + (e.key === "ArrowDown" ? 1 : STEPS.length - 1)) % STEPS.length;
                  setActive(n);
                  document.getElementById(`tab-${STEPS[n].id}`)?.focus();
                }}>
                <span className="step-num">{i + 1}</span>
                <span>{s.title}</span>
              </button>
            ))}
          </div>
          <div id="step-panel" role="tabpanel" aria-labelledby={`tab-${step.id}`} className="panel step-panel" key={step.id}>
            <div className="step-icon"><Icon name={step.icon} size={26} /></div>
            <h2>{step.title}</h2>
            <p className="step-summary">{step.summary}</p>
            <ul>{step.points.map((p) => <li key={p}>{p}</li>)}</ul>
            {step.id === "marked" && total != null && <p className="live-fact">The Engine has {total.toLocaleString()} tickets loaded right now across {cities.data?.length} cities.</p>}
            <div className="status-row" aria-label="What is real in this step">
              {step.status.map((s) => <span key={s.text} className={`tag tag-${s.kind}`}><b>{KIND_LABEL[s.kind]}</b> {s.text}</span>)}
            </div>
          </div>
        </div>

        <FusionExample />

        <div className="pub-cta">
          <p>Want to see it run on real code and real photos?</p>
          <Link className="btn btn-primary" to="/platform">Explore the platform</Link>
        </div>
      </main>
    </div>
  );
}
