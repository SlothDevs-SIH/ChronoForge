import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useMemo } from "react";
import { api } from "../api";
import type { Score } from "../types";

// Only the synthetic cities carry a calibrated probability. Everything else is a rank or a bounded prior,
// so it must not be shown as a percentage chance.
function riskCell(s: Score): { text: string; kind: string } {
  switch (s.score_type) {
    case "calibrated_probability":
      return { text: `${(s.p_false_closure * 100).toFixed(0)}% (synthetic)`, kind: "calibrated" };
    case "risk_rank_prior":
      return { text: `risk rank ${Math.round((s.risk_percentile ?? 0) * 100)}th percentile`, kind: "rank" };
    case "rule_flags":
      return { text: s.flags?.length ? `flag: ${s.flags.join(", ")}` : "no flag", kind: "flag" };
    default:
      return { text: "not scored", kind: "none" };
  }
}

function shortRisk(s: Score): string {
  if (s.score_type === "calibrated_probability") return `${Math.round(s.p_false_closure * 100)}%`;
  if (s.score_type === "risk_rank_prior") return `rank ${Math.round((s.risk_percentile ?? 0) * 100)}`;
  if (s.score_type === "rule_flags") return s.flags?.length ? "flagged" : "no flag";
  return "unscored";
}

// Reopen rate per category from the city records: a single-hue bar list with direct labels and a table underneath.
function ReopenChart({ city }: { city: string }) {
  const { data, isPending, error } = useQuery({ queryKey: ["wards", city], queryFn: () => api.wardStats(city || undefined), retry: false });
  const rows = useMemo(() => {
    const by = new Map<string, { closed: number; reopened: number }>();
    for (const w of data ?? []) {
      const r = by.get(w.category) ?? { closed: 0, reopened: 0 };
      r.closed += w.closed ?? 0; r.reopened += w.reopened ?? 0;
      by.set(w.category, r);
    }
    return [...by.entries()].filter(([, r]) => r.closed >= 50).map(([category, r]) => ({ category, ...r, rate: r.reopened / r.closed })).sort((a, b) => b.rate - a.rate).slice(0, 8);
  }, [data]);
  if (isPending) return <p className="muted">Loading city records…</p>;
  if (error || !rows.length) return <p className="muted">No category has enough closed tickets to compare.</p>;
  const max = Math.max(...rows.map((r) => r.rate), 0.001);
  return (
    <>
      <ul className="bars" aria-label="Reopen rate by category">
        {rows.map((r) => <li key={r.category}><span className="bar-name">{r.category}</span><span className="bar-track"><i style={{ width: `${(r.rate / max) * 100}%` }} /></span><b>{(r.rate * 100).toFixed(1)}%</b></li>)}
      </ul>
      <details className="bars-table"><summary>Show as a table</summary>
        <table><thead><tr><th>Category</th><th className="num">Closed</th><th className="num">Reopened</th><th className="num">Rate</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.category}><td>{r.category}</td><td className="num">{r.closed.toLocaleString()}</td><td className="num">{r.reopened.toLocaleString()}</td><td className="num">{(r.rate * 100).toFixed(1)}%</td></tr>)}</tbody></table>
      </details>
      <p className="fine">Share of closed tickets later reopened by the citizen, from the city's own records. Categories with fewer than 50 closed tickets are left out.</p>
    </>
  );
}

export default function Triage({ city, overview = false }: { city: string; overview?: boolean }) {
  const pending = useQuery({ queryKey: ["approvals", "pending"], queryFn: () => api.approvals("pending"), retry: false, enabled: overview });
  const { data, error, isLoading } = useQuery({ queryKey: ["tickets", city], queryFn: () => api.tickets(city || undefined, "closed", 100, "risk") });
  if (isLoading) return <div className="loading-state">Loading the verification queue…</div>;
  if (error) return <div className="error-state">Could not reach the Engine on :8001. Is it running? ({String(error)})</div>;
  const rows = data ?? [];
  const risky = rows.filter(({ score }) => score.flags?.length || score.p_false_closure >= .7).length;
  const synthetic = rows.filter(({ score }) => score.score_type === "calibrated_probability").length;
  const shown = overview ? rows.slice(0, 7) : rows;
  return (
    <>
      <div className="page-heading"><div><h1>{overview ? "City overview" : "Triage queue"}</h1><p>{overview ? "A calm view of the cases that need independent verification." : "Closed tickets ranked by risk. For real cities this is a rank, not a probability."}</p></div>{overview && <Link className="button button-primary button-small" to={`/triage${city ? `?city=${city}` : ""}`}>Open the triage queue</Link>}</div>
      {overview && <div className="metric-grid"><div className="metric-card"><span>Highest-risk tickets loaded</span><strong>{rows.length.toLocaleString()}</strong><small>Top {rows.length} by risk, not the whole city</small></div><div className="metric-card"><span>Needs review</span><strong>{risky}</strong><small>With a flag or high risk signal</small></div><div className="metric-card"><span>Evidence-ready</span><strong>{synthetic}</strong><small>Have a calibrated (synthetic) probability</small></div><div className="metric-card"><span>Awaiting approval</span><strong>{pending.data ? pending.data.length : "—"}</strong><small>{pending.data ? "Recommendations a person must decide" : "Agent not reachable"}</small></div></div>}
      {overview ? <div className="dashboard-grid"><section className="app-card"><div className="app-card-header"><h2>Reopen rate by category</h2><span className={`badge ${city ? "" : "synthetic"}`}>{city ? "City records" : "All cities, includes synthetic"}</span></div><div className="app-card-body"><ReopenChart city={city} /></div></section><section className="app-card"><div className="app-card-header"><h2>Priority queue</h2><Link className="text-link" to={`/triage${city ? `?city=${city}` : ""}`}>See all</Link></div><div className="app-card-body"><div className="priority-list">{shown.slice(0, 4).map(({ ticket, score }) => <Link className="priority-item" to={`/ticket/${ticket.ticket_id}`} key={ticket.ticket_id}><span className="priority-icon">{score.p_false_closure >= .7 ? "!" : "·"}</span><span><strong>{ticket.ticket_id}</strong><small>{ticket.category} · {ticket.ward}</small></span><b>{shortRisk(score)}</b></Link>)}</div></div></section></div> : null}
      <section className="content-card"><div className="app-card-header"><h2>{overview ? "Recent closed tickets" : "Closed tickets ranked by risk"}</h2><span className="badge">{rows.length} loaded</span></div><div className="table-wrap"><table><thead><tr><th>Ticket</th><th>City</th><th>Ward</th><th>Category</th><th>Risk</th><th>Score type</th></tr></thead><tbody>{shown.map(({ ticket, score }) => <tr key={ticket.ticket_id}><td><Link className="table-link" to={`/ticket/${ticket.ticket_id}`}>{ticket.ticket_id}</Link></td><td>{ticket.city} <span className={`badge ${ticket.data_quality}`}>{ticket.data_quality}</span></td><td>{ticket.ward}</td><td>{ticket.category}</td><td><span className="risk-meter"><span><i style={{ width: `${Math.min(100, Math.max(10, score.p_false_closure * 100))}%` }} /></span>{riskCell(score).text}</span></td><td><span className="badge">{score.score_type.replace(/_/g, " ")}</span></td></tr>)}</tbody></table></div></section>
    </>
  );
}
