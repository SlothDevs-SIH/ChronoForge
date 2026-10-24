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
