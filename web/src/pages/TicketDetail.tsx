import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Icon, { type IconName } from "../components/Icon";
import { useToast } from "../components/Toast";
import type { Score, Ticket, TraceEvent } from "../types";

function prettyFeature(feature: string) {
  return feature.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

// The number in the ring means different things per score type. Only synthetic cities have a probability.
function describeScore(score?: Score) {
  if (!score) return { ring: 0, big: "—", small: "waiting", label: "Waiting for score", headline: "Scoring…", copy: "" };
  const pct = Math.round((score.risk_percentile ?? 0) * 100);
  switch (score.score_type) {
    case "calibrated_probability":
      return { ring: score.p_false_closure, big: `${Math.round(score.p_false_closure * 100)}%`, small: "probability (synthetic)", label: "Calibrated probability, synthetic data", headline: score.p_false_closure >= 0.7 ? "Needs independent review" : "Keep evidence in context",
        copy: "Calibrated on synthetic tickets only. It prioritises attention; the agent still has to collect an independent check." };
    case "risk_rank_prior":
      return { ring: score.risk_percentile ?? 0, big: `${pct}th`, small: "percentile risk rank", label: "Risk rank, not a probability", headline: pct >= 90 ? "Needs independent review" : "Keep evidence in context",
        copy: "Where this closure sits among closed tickets in the city. The model is a weak signal (test AUROC about 0.60 to 0.64): it orders the queue and does not say how likely the repair failed." };
    case "rule_flags":
      return { ring: 0, big: score.flags?.length ? "Flag" : "None", small: "rule flags", label: score.flags?.length ? score.flags.join(", ") : "No rule flags", headline: score.flags?.length ? "Needs independent review" : "Keep evidence in context",
        copy: "A rule on how the ticket was closed, not a probability. Flagged closures are about twice as likely to be reopened, which is a reason to look, not a verdict." };
    default:
      return { ring: 0, big: "—", small: "not scored", label: "Not scored", headline: "No model applies", copy: "No scorer covers this ticket, so the independent checks carry the decision." };
  }
}

function Tile({ title, icon, tone = "neutral", children, meta }: { title: string; icon: IconName; tone?: "neutral" | "warning" | "success"; children: ReactNode; meta?: string }) {
  return <article className="evidence-tile"><span className={`evidence-tile-icon tone-${tone}`}><Icon name={icon} size={18} /></span><div><h3>{title}</h3><div className="tile-copy">{children}</div>{meta && <small>{meta}</small>}</div></article>;
}

function SatelliteTile({ ticket, score }: { ticket: Ticket; score?: Score }) {
  const eligible = Boolean(score?.satellite_eligible);
  const { data, isPending } = useQuery({ queryKey: ["sat", ticket.ticket_id], queryFn: () => api.satelliteCheck(ticket.ticket_id, true), enabled: eligible, retry: false });
  if (!score) return <Tile title="Satellite context" icon="satellite"><p>Waiting for the score.</p></Tile>;
  if (!eligible) return <Tile title="Satellite context" icon="satellite" meta="Skipped, cost 0"><p>{score.satellite_reason?.replace(/^not applicable: /i, "Not checkable from orbit: ") ?? "Not checkable from orbit for this issue type."}</p></Tile>;
  const stored = data && data.verdict !== "inconclusive";
  return (
    <Tile title="Satellite context" icon="satellite" tone={stored ? "warning" : "neutral"} meta="Sentinel-2, cost 3 when run">
      {isPending ? <p>Looking for a stored result…</p> : stored
        ? <><p>{data.verdict === "contradicts_fix" ? "No change is visible at the site after closure." : "A change is visible at the site after closure."} Likelihood ratio {data.likelihood_ratio}.</p>
            <div className="evidence-photos">{(["before", "after"] as const).map((w) => <figure key={w}><img src={api.satelliteChip(ticket.ticket_id, w)} alt={`Satellite view ${w} closure`} loading="lazy" onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = "none"; }} /><figcaption>{w === "before" ? "Before closure" : "After closure"}</figcaption></figure>)}</div></>
        : <p>Eligible, but no stored result yet. The agent runs the live check (10 to 60 seconds) and abstains if clouds hide the site.</p>}
    </Tile>
  );
}

export default function TicketDetail() {
  const { id = "" } = useParams();
  const toast = useToast();
  const { data: ticket, error: ticketError } = useQuery({ queryKey: ["ticket", id], queryFn: () => api.ticket(id), refetchInterval: 3000 });
  const { data: score } = useQuery({ queryKey: ["score", id], queryFn: () => api.score(id), enabled: Boolean(id) });
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const close = useRef<(() => void) | undefined>();
  useEffect(() => () => close.current?.(), []);

  async function run() {
    setEvents([]);
    setRunning(true);
    try {
      const { run_id } = await api.startRun(id);
      close.current = api.streamRun(run_id, (event) => setEvents((previous) => [...previous, event]), () => { setRunning(false); toast("success", `Verification finished for ${id}.`); });
    } catch {
      setRunning(false);
      toast("error", "The Agent could not start a run. Check that it is running on port 8002.");
    }
  }

  const last = events[events.length - 1];
  const desc = describeScore(score);
  const needsApproval = events.some((e) => e.type === "approval_needed");
  const citizenEvent = [...events].reverse().find((e) => e.tool?.includes("citizen"));
  const photoEvent = [...events].reverse().find((e) => e.tool?.includes("photo"));
  if (ticketError) return <div className="error-state">Could not load this ticket. Check that the Engine is running on port 8001. ({String(ticketError)})</div>;
  if (!ticket) return <div className="loading-state">Loading ticket evidence…</div>;

  return (
    <>
      <div className="breadcrumb"><Link to="/dashboard">Overview</Link><span>/</span><Link to="/triage">Triage queue</Link><span>/</span><strong>{ticket.ticket_id}</strong></div>
      <div className="page-heading detail-heading"><div><h1>{ticket.ticket_id}</h1><p>{ticket.text}</p></div><span className={`status-badge status-${ticket.status}`}><span /> {ticket.status}</span></div>

      <div className="detail-layout">
        <div className="detail-main">
          <section className="app-card score-card">
            <div className="app-card-header"><h2>Closure integrity signal</h2><span className={`badge ${ticket.data_quality}`}>{ticket.data_quality} data</span></div>
            <div className="score-card-body"><div className={`score-ring ${desc.ring === 0 ? "score-ring-flat" : ""}`} style={{ "--score": `${Math.round(desc.ring * 100)}%` } as CSSProperties}><strong>{desc.big}</strong><small>{desc.small}</small></div><div className="score-copy"><p className="eyebrow">{desc.label}</p><h2>{desc.headline}</h2><p>{desc.copy}</p></div></div>
            {score && score.score_type !== "rule_flags" && <div className="reason-list">{score.reasons.slice(0, 4).map((reason) => <div className="reason-row" key={reason.feature}><span>{prettyFeature(reason.feature)}</span><b>{String(reason.value ?? "—")}</b><i style={{ width: `${Math.min(100, Math.max(8, Math.abs(reason.shap ?? 0) * 220))}%` }} /></div>)}</div>}
          </section>

          <section className="app-card evidence-card">
            <div className="app-card-header"><div><h2>Evidence register</h2><small className="header-caption">Sources and limitations stay visible</small></div><span className="badge">{score?.eligible_checks?.length ?? 0} checks eligible</span></div>
            <div className="evidence-grid">
              <Tile title="Photo verification" icon="photo" meta={photoEvent ? `Agent: ${photoEvent.summary}` : ticket.closure_photo_url ? "Closure photo on record" : "No closure photo in this city's records"}>
                {ticket.city === "demo" && ticket.closure_photo_url
                  ? <div className="evidence-photos">{(["before", "after"] as const).map((w) => <figure key={w}><img src={api.demoPhoto(ticket.ticket_id, w)} alt={w === "before" ? "Photo of the problem as reported" : "Photo attached at closure"} loading="lazy" /><figcaption>{w === "before" ? "As reported" : "At closure"}</figcaption></figure>)}</div>
                  : <p>{ticket.closure_photo_url ? "A closure photo reference exists, but the file is not available here." : "This city's records carry no closure photo, so the photo check cannot run."}</p>}
              </Tile>
              <SatelliteTile ticket={ticket} score={score} />
              <Tile title="Citizen feedback" icon="chat" meta="Asked on Telegram; WhatsApp is not built"><p>{citizenEvent ? citizenEvent.summary : "A citizen reply counts as evidence, never as automatic truth. No reply has been collected for this ticket."}</p></Tile>
              <Tile title="Human review" icon="person" tone={needsApproval ? "warning" : "success"} meta="Required before any reopen or escalation"><p>{needsApproval ? <>The agent recommends an action. <Link className="text-link" to="/approvals">Decide in the approval queue</Link>.</> : "Any reopen or escalation waits for a person to approve it."}</p></Tile>
            </div>
          </section>
        </div>

        <aside className="detail-rail">
          <section className="app-card agent-card"><div className="app-card-header"><div><h2>Agent trace</h2><small className="header-caption">Budgeted, observable decisions</small></div><span className={`live-dot ${running ? "is-running" : ""}`}><span />{running ? "Running" : "Ready"}</span></div><div className="agent-card-body"><div className="budget-row"><span>Verification budget</span><strong>{last ? `${last.budget_left} / 10 left` : "10 / 10 left"}</strong></div><div className="budget-bar"><span style={{ width: `${((last?.budget_left ?? 10) / 10) * 100}%` }} /></div><button onClick={run} disabled={running}>{running ? "Collecting evidence…" : "Run verification agent"}</button>{events.length === 0 && <div className="trace-empty"><span className="trace-empty-icon"><Icon name="list" size={18} /></span><strong>No run started</strong><p>Start a run to see tool choice, evidence and posterior updates here.</p></div>}<ol className="trace">{events.map((event) => <li key={`${event.run_id}-${event.step}`}><span className={`trace-marker trace-${event.type}`} /> <div><strong>{event.tool ?? event.type.replace(/_/g, " ")}</strong><p>{event.summary}</p><small>{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {event.budget_left} budget left</small></div></li>)}</ol></div></section>
          <section className="app-card case-meta"><div className="app-card-header"><h2>Case metadata</h2></div><dl><div><dt>Category</dt><dd>{ticket.category}</dd></div><div><dt>Ward</dt><dd>{ticket.ward}</dd></div><div><dt>Created</dt><dd>{new Date(ticket.created_at).toLocaleDateString()}</dd></div><div><dt>Closed</dt><dd>{ticket.closed_at ? new Date(ticket.closed_at).toLocaleDateString() : "Not closed"}</dd></div><div><dt>Closure note</dt><dd>{ticket.closure_note ?? "None provided"}</dd></div></dl></section>
        </aside>
      </div>
    </>
  );
}
