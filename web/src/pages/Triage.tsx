import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import WardMap from "../components/WardMap";
import ComplaintCard, { riskPin } from "../components/ComplaintCard";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { api } from "../api";
import PeriodSwitch from "../components/PeriodSwitch";
import { usePeriod } from "../hooks/usePeriod";
import type { Score, TicketWithScore } from "../types";

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
  const { days } = usePeriod();
  const { data, isPending, error } = useQuery({ queryKey: ["wards", city, days], queryFn: () => api.wardStats(city || undefined, days), retry: false });
  const rows = useMemo(() => {
    const by = new Map<string, { closed: number; reopened: number }>();
    for (const w of data ?? []) {
      const r = by.get(w.category) ?? { closed: 0, reopened: 0 };
      r.closed += w.closed ?? 0; r.reopened += w.reopened ?? 0;
      by.set(w.category, r);
    }
    return [...by.entries()].filter(([, r]) => r.closed >= 50).map(([category, r]) => ({ category, ...r, rate: r.reopened / r.closed })).sort((a, b) => b.rate - a.rate).slice(0, 8);
  }, [data]);
  if (isPending) return <Skeleton rows={4} label="Loading city records" />;
  if (error) return <ErrorState error={error} title="We couldn't load the city records" />;
  if (!rows.length) return <EmptyState title="Nothing to compare">No category has enough closed tickets to compare.</EmptyState>;
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

const SCORE_LABEL: Record<Score["score_type"], string> = { baseline: "No model applies", risk_rank_prior: "Risk rank", rule_flags: "Rule flag", calibrated_probability: "Synthetic probability" };
const PAGE = 25;
const CATEGORIES = ["pothole", "garbage", "streetlight", "drain", "water_leak", "other"];

function Queue({ city, rows, loading, error, retry, page, setPage, hasNext }: {
  city: string; rows: TicketWithScore[]; loading: boolean; error: unknown; retry: () => void; page: number; setPage: (n: number) => void; hasNext: boolean;
}) {
  const [view, setView] = useState<"cards" | "table">("cards");
  if (loading) return <div className="app-card-body"><Skeleton rows={6} label="Loading the verification queue" /></div>;
  if (error) return <div className="app-card-body"><ErrorState error={error} onRetry={retry} title="We couldn't load the queue" /></div>;
  if (!rows.length) return <div className="app-card-body"><EmptyState title="No tickets match these filters">Try a different status, category or time window.</EmptyState></div>;
  return (
    <>
      <div className="view-bar"><span className="muted">{rows.length} tickets</span>
        <div className="view-toggle" role="group" aria-label="View"><button type="button" aria-pressed={view === "cards"} onClick={() => setView("cards")}>Cards</button><button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button></div></div>
      {view === "cards" ? (
        <div className="app-card-body"><div className="cutout-grid" aria-label="Tickets in the verification queue">{rows.map(({ ticket, score }) => (
          <ComplaintCard key={ticket.ticket_id} ticket={ticket} to={`/ticket/${ticket.ticket_id}`} actionLabel="Review ticket" pin={score.score_type === "baseline" ? undefined : riskPin(score)} note={SCORE_LABEL[score.score_type]} />
        ))}</div></div>
      ) : (
        <div className="table-wrap"><table>
          <thead><tr><th>Ticket</th><th>City</th><th>Ward</th><th>Category</th><th>Closed</th><th>Risk</th><th>Score type</th></tr></thead>
          <tbody>{rows.map(({ ticket, score }) => (
            <tr key={ticket.ticket_id}>
              <td><Link className="table-link" to={`/ticket/${ticket.ticket_id}`}>{ticket.ticket_id}</Link></td>
              <td>{ticket.city} <span className={`badge ${ticket.data_quality}`}>{ticket.data_quality}</span></td>
              <td>{ticket.ward}</td><td>{ticket.category}</td>
              <td>{ticket.closed_at ? new Date(ticket.closed_at).toLocaleDateString() : "Not closed"}</td>
              <td><span className="risk-meter"><span><i style={{ width: `${Math.min(100, Math.max(10, score.p_false_closure * 100))}%` }} /></span>{riskCell(score).text}</span></td>
              <td><span className="badge">{score.score_type.replace(/_/g, " ")}</span></td>
            </tr>))}</tbody>
        </table></div>
      )}
      {(page > 0 || hasNext) && (
        <div className="pager">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page + 1}{city ? ` in ${city}` : ""}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={!hasNext} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </>
  );
}

/** `?city=..&period=..` for a link that keeps both. */
function keepQuery(city: string, period: string) {
  const q = new URLSearchParams();
  if (city) q.set("city", city);
  if (period) q.set("period", period);
  return q.size ? `?${q}` : "";
}

export default function Triage({ city, overview = false }: { city: string; overview?: boolean }) {
  const nav = useNavigate();
  const [status, setStatus] = useState("closed");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<"risk" | "newest">("risk");
  const [minScore, setMinScore] = useState("0");
  const period = usePeriod();
  const [page, setPage] = useState(0);
  const [find, setFind] = useState("");
  const onFilter = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(0); };

  const pending = useQuery({ queryKey: ["approvals", "pending"], queryFn: () => api.approvals("pending"), retry: false, enabled: overview });
  const top = useQuery({ queryKey: ["tickets", "top", city, period.days], queryFn: () => api.tickets(city || undefined, "closed", 100, "risk", 0, period.days ? { window_days: String(period.days) } : {}), enabled: overview, retry: false });
  const list = useQuery({
    queryKey: ["tickets", "queue", city, status, category, sort, minScore, period.days, page],
    queryFn: () => api.tickets(city || undefined, status || undefined, PAGE, sort, page * PAGE, { ...(category ? { category } : {}), ...(Number(minScore) > 0 ? { min_score: minScore } : {}), ...(period.days ? { window_days: String(period.days) } : {}) }),
    enabled: !overview, retry: false, placeholderData: (prev) => prev,
  });

  if (overview) {
    if (top.isLoading) return <><div className="page-heading"><div><h1>City overview</h1></div></div><Skeleton rows={6} label="Loading the overview" /></>;
    if (top.error) return <ErrorState error={top.error} onRetry={() => void top.refetch()} title="We couldn't load the overview" />;
    const rows = top.data ?? [];
    const risky = rows.filter(({ score }) => score.flags?.length || score.p_false_closure >= 0.7).length;
    const synthetic = rows.filter(({ score }) => score.score_type === "calibrated_probability").length;
    const mapCity = city || "bengaluru";
    const synthCity = ["pune", "synthetic", "demo"].includes(mapCity);
    return (
      <>
        <div className="page-heading"><div><h1>City overview</h1><p>The cases that need independent verification.</p></div><Link className="btn btn-primary btn-sm" to={`/triage${keepQuery(city, period.value)}`}>Open the triage queue</Link></div>
        <PeriodSwitch />
        <div className="metric-grid">
          <div className="metric-card"><span>Highest-risk tickets loaded</span><strong>{rows.length.toLocaleString()}</strong><small>Top {rows.length} by risk, not the whole city</small></div>
          <div className="metric-card"><span>Needs review</span><strong>{risky}</strong><small>With a flag or high risk signal</small></div>
          <div className="metric-card"><span>Evidence-ready</span><strong>{synthetic}</strong><small>Have a calibrated (synthetic) probability</small></div>
          <div className="metric-card"><span>Awaiting approval</span><strong>{pending.data ? pending.data.length : "—"}</strong><small>{pending.data ? "Recommendations a person must decide" : "Not available right now"}</small></div>
        </div>
        <div className="dashboard-grid">
          <section className="app-card"><div className="app-card-header"><h2>Ward map: {mapCity[0].toUpperCase() + mapCity.slice(1)}</h2><span className={`badge ${synthCity ? "synthetic" : "real"}`}>{synthCity ? "Synthetic city" : "Real records"}</span></div><div className="app-card-body"><WardMap city={mapCity} />{!city && <p className="fine">Showing Bengaluru. Pick another city in the bar above to change the map.</p>}</div></section>
          <section className="app-card"><div className="app-card-header"><h2>Priority queue</h2><Link className="text-link" to={`/triage${keepQuery(city, period.value)}`}>See all</Link></div><div className="app-card-body">
            {rows.length === 0 ? <EmptyState title="Nothing to review">No closed tickets are loaded for this view.</EmptyState> :
              <div className="priority-list">{rows.slice(0, 4).map(({ ticket, score }) => <Link className="priority-item" to={`/ticket/${ticket.ticket_id}`} key={ticket.ticket_id}><span className="priority-icon">{score.p_false_closure >= 0.7 ? "!" : "·"}</span><span><strong>{ticket.ticket_id}</strong><small>{ticket.category} · {ticket.ward}</small></span><b>{shortRisk(score)}</b></Link>)}</div>}
          </div></section>
        </div>
        <div className="chart-row"><section className="app-card"><div className="app-card-header"><h2>Reopen rate by category</h2><span className={`badge ${synthCity ? "synthetic" : "real"}`}>{mapCity[0].toUpperCase() + mapCity.slice(1)}</span></div><div className="app-card-body"><ReopenChart city={mapCity} /></div></section></div>
        <section className="content-card"><div className="app-card-header"><h2>Highest-risk closed tickets</h2><span className="badge">{Math.min(rows.length, 7)} shown</span></div>
          <Queue city={city} rows={rows.slice(0, 7)} loading={false} error={null} retry={() => undefined} page={0} setPage={() => undefined} hasNext={false} /></section>
      </>
    );
  }

  const rows = list.data ?? [];
  return (
    <>
      <div className="page-heading"><div><h1>Triage queue</h1><p>Closed tickets ranked by risk. For real cities this is a rank, not a probability.</p></div>
        <form className="find" onSubmit={(e) => { e.preventDefault(); if (find.trim()) nav(`/ticket/${encodeURIComponent(find.trim())}`); }}>
          <label htmlFor="find-ticket" className="sr-only">Find a ticket by id</label>
          <input id="find-ticket" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a ticket id" />
          <button type="submit" className="btn btn-secondary btn-sm" disabled={!find.trim()}>Open</button>
        </form></div>
      <div className="filters" role="group" aria-label="Filters">
        <label>Status<select value={status} onChange={(e) => onFilter(setStatus)(e.target.value)}><option value="closed">Closed</option><option value="reopened">Reopened</option><option value="open">Open</option><option value="">Any</option></select></label>
        <label>Category<select value={category} onChange={(e) => onFilter(setCategory)(e.target.value)}><option value="">All</option>{CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select></label>
        <label>Sort by<select value={sort} onChange={(e) => onFilter(setSort)(e.target.value as "risk" | "newest")}><option value="risk">Highest risk</option><option value="newest">Newest</option></select></label>
        <label>Minimum score<select value={minScore} onChange={(e) => onFilter(setMinScore)(e.target.value)}><option value="0">Any</option><option value="0.4">0.4 or higher</option><option value="0.6">0.6 or higher</option><option value="0.8">0.8 or higher</option></select></label>
      </div>
      <PeriodSwitch onChange={() => setPage(0)} />
      <section className="content-card"><div className="app-card-header"><h2>Tickets</h2><span className="badge">{rows.length} on this page</span></div>
        <Queue city={city} rows={rows} loading={list.isLoading} error={list.error} retry={() => void list.refetch()} page={page} setPage={setPage} hasNext={(list.data?.length ?? 0) === PAGE} /></section>
    </>
  );
}
