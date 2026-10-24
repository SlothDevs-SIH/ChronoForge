import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function AuditLog() {
  const verify = useQuery({ queryKey: ["audit", "verify"], queryFn: api.auditVerify, refetchInterval: 5000, retry: false });
  const log = useQuery({ queryKey: ["audit"], queryFn: api.audit, refetchInterval: 5000, retry: false });
  if (log.error) return <div className="error-state">Could not reach the Agent on port 8002, so the audit log is unavailable. Start it and this page recovers by itself.</div>;
  const rows = [...(log.data ?? [])].reverse().slice(0, 60);
  return (
    <>
      <div className="page-heading"><div><h1>Audit log</h1><p>Every agent step and every human decision, chained by hash so an edit anywhere breaks the chain.</p></div>
        {verify.data && <span className={`status-badge ${verify.data.ok ? "status-approved" : "status-rejected"}`} role="status"><span /> {verify.data.ok ? `Chain intact, ${verify.data.length} entries` : `Chain broken at entry ${verify.data.first_broken_idx}`}</span>}</div>
      {log.isPending && <div className="loading-state">Loading the audit log…</div>}
      {log.data && !rows.length && <div className="empty-state"><strong>No entries yet.</strong><p>Entries appear when the agent runs or someone decides an approval.</p></div>}
      {rows.length > 0 && <section className="content-card"><div className="app-card-header"><h2>Latest entries</h2><span className="badge">showing {rows.length} of {log.data?.length}</span></div>
        <div className="table-wrap"><table><thead><tr><th>#</th><th>Time</th><th>Event</th><th>Ticket</th><th>Hash</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.idx}><td>{r.idx}</td><td>{new Date(r.ts).toLocaleString()}</td><td>{String(r.event.type ?? "event").replace(/_/g, " ")}</td><td>{r.event.ticket_id ? String(r.event.ticket_id) : "—"}</td><td><code>{r.hash.slice(0, 10)}</code></td></tr>)}</tbody></table></div></section>}
    </>
  );
}
