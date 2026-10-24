import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ROLE_LABEL } from "../auth";
import { useToast } from "../components/Toast";

export default function Admin() {
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const agent = useQuery({ queryKey: ["agent-health"], queryFn: api.agentHealth, retry: false });
  const engine = useQuery({ queryKey: ["engine-health"], queryFn: api.engineHealth, retry: false });
  const set = useMutation({
    mutationFn: (v: { id: string; status: "active" | "disabled" }) => api.setUserStatus(v.id, v.status),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["users"] }); toast("success", "Account updated."); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not update the account."),
  });
  const web = useQuery({ queryKey: ["web-requests"], queryFn: () => api.tickets("web", undefined, 50, "newest"), refetchInterval: 5000 });
  const close = useMutation({
    mutationFn: api.closeRequest,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["web-requests"] }); toast("success", "Marked closed. The case watcher will check it within seconds."); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not close the request."),
  });
  const [days, setDays] = useState(7);
  const digest = useQuery({ queryKey: ["summary", days], queryFn: () => api.summary(days), retry: false, refetchInterval: 15000 });
  const rows = users.data ?? [];
  const pending = rows.filter((u) => u.status === "pending");
  const up = (q: { data?: { ok: boolean }; isLoading: boolean }) => (q.data?.ok ? "Up" : q.isLoading ? "…" : "Down");
  return (
    <>
      <div className="page-heading"><div><h1>Administration</h1><p>Approve officers, manage accounts and check that the services are up.</p></div>
        <Link className="button button-primary button-small" to="/dashboard">Officer overview</Link></div>
      <div className="metric-grid">
        <div className="metric-card"><span>Accounts</span><strong>{users.data ? rows.length : "—"}</strong></div>
        <div className="metric-card"><span>Officers awaiting approval</span><strong>{users.data ? pending.length : "—"}</strong></div>
        <div className="metric-card"><span>Engine service</span><strong>{up(engine)}</strong></div>
        <div className="metric-card"><span>Agent service</span><strong>{up(agent)}</strong></div>
      </div>
      <section className="content-card"><div className="app-card-header"><h2>Digest</h2>
        <div className="seg" role="group" aria-label="Period">{[7, 30].map((d) => <button key={d} className={days === d ? "is-on" : ""} onClick={() => setDays(d)}>{d} days</button>)}</div></div>
        <div className="app-card-body">
          {digest.isLoading && <p className="muted">Loading…</p>}
          {digest.error && <p className="muted">The digest is not available right now.</p>}
          {digest.data && <>
            <p className="digest-text">{digest.data.text}</p>
            <div className="digest-grid">{Object.entries(digest.data.labels).map(([k, label]) => <div key={k}><strong>{digest.data.counts[k] ?? 0}</strong><span>{label}</span></div>)}</div>
            {digest.data.messages.failed > 0 && <p className="auth-error">{digest.data.messages.failed} citizen messages could not be delivered{digest.data.messages.pending ? `, ${digest.data.messages.pending} still retrying` : ""}.</p>}
          </>}
        </div>
      </section>
      <section className="content-card"><div className="app-card-header"><h2>Website requests</h2><span className="badge">simulated city</span></div>
        <div className="table-wrap"><table><thead><tr><th>Request</th><th>Problem</th><th>Status</th><th /></tr></thead><tbody>
          {web.data?.length === 0 && <tr><td colSpan={4}>No requests filed on the website yet.</td></tr>}
          {web.data?.map(({ ticket: t }) => (
            <tr key={t.ticket_id}><td><a className="table-link" href={`/ticket/${t.ticket_id}`}>{t.ticket_id}</a></td><td>{t.text}</td><td><span className="badge">{t.status}</span></td>
              <td className="num">{t.status === "open" && <button className="btn btn-secondary btn-sm" onClick={() => close.mutate(t.ticket_id)} disabled={close.isPending}>Mark closed (as the city)</button>}</td></tr>
          ))}
        </tbody></table></div>
        <p className="fine" style={{ padding: "0 16px 14px" }}>Stands in for the city closing a request. Once closed, TrueClose checks it and an administrator decides on the reopen from Approvals.</p>
      </section>
      {users.isLoading && <div className="loading-state">Loading accounts…</div>}
      {users.error && <div className="error-state">Could not load accounts. ({String(users.error)})</div>}
      {users.data && (
        <section className="content-card"><div className="app-card-header"><h2>Accounts</h2></div>
          <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead><tbody>
            {rows.map((u) => (
              <tr key={u.user_id}><td>{u.name}</td><td>{u.email}</td><td>{ROLE_LABEL[u.role]}</td><td><span className="badge">{u.status}</span></td>
                <td className="num">{u.role !== "admin" && (u.status === "active"
                  ? <button className="btn btn-secondary btn-sm" onClick={() => set.mutate({ id: u.user_id, status: "disabled" })}>Disable</button>
                  : <button className="btn btn-primary btn-sm" onClick={() => set.mutate({ id: u.user_id, status: "active" })}>{u.status === "pending" ? "Approve" : "Enable"}</button>)}</td></tr>
            ))}
          </tbody></table></div></section>
      )}
    </>
  );
}
