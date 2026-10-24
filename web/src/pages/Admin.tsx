import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { StatusDot } from "../components/ConnectionBadge";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { useToast } from "../components/Toast";
import { useConnection } from "../hooks/useConnection";
import { userMessage } from "../lib/http";
import type { AdminUser, Role } from "../types";

function UserRow({ u }: { u: AdminUser }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [ticket, setTicket] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });
  const fail = (e: unknown) => toast("error", userMessage(e));
  const approve = useMutation({ mutationFn: () => api.approveUser(u.user_id), onSuccess: () => { toast("success", `Approved ${u.email}.`); void refresh(); }, onError: fail });
  const reject = useMutation({ mutationFn: () => api.rejectUser(u.user_id), onSuccess: () => { toast("success", `Rejected ${u.email}.`); void refresh(); }, onError: fail });
  const setRole = useMutation({ mutationFn: (role: Role) => api.setUserRole(u.user_id, role), onSuccess: () => { toast("success", `Role updated for ${u.email}.`); void refresh(); }, onError: fail });
  const link = useMutation({ mutationFn: () => api.linkTicket(u.user_id, ticket.trim()), onSuccess: () => { toast("success", `Linked ${ticket.trim()} to ${u.email}.`); setTicket(""); void refresh(); }, onError: fail });
  const unlink = useMutation({ mutationFn: (t: string) => api.unlinkTicket(u.user_id, t), onSuccess: () => { toast("success", "Ticket unlinked."); void refresh(); }, onError: fail });

  return (
    <tr>
      <td>{u.email}</td>
      <td>
        <label className="sr-only" htmlFor={`role-${u.user_id}`}>Role for {u.email}</label>
        <select id={`role-${u.user_id}`} value={u.role} disabled={setRole.isPending} onChange={(e) => setRole.mutate(e.target.value as Role)}>
          <option value="citizen">Citizen</option><option value="officer">Officer</option><option value="admin">Admin</option>
        </select>
      </td>
      <td><span className={`status-badge status-${u.status === "active" ? "approved" : u.status === "pending" ? "cannot_tell" : "rejected"}`}><span /> {u.status}</span></td>
      <td>
        {u.status === "pending" && <div className="row-actions">
          <button type="button" className="btn btn-primary btn-sm" disabled={approve.isPending} onClick={() => approve.mutate()}>Approve</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={reject.isPending} onClick={() => reject.mutate()}>Reject</button>
        </div>}
        {u.role === "citizen" && u.status === "active" && (
          <div className="link-box">
            <ul className="ticket-chips">{(u.ticket_ids ?? []).map((t) => <li key={t}>{t} <button type="button" aria-label={`Unlink ${t} from ${u.email}`} onClick={() => unlink.mutate(t)}>×</button></li>)}</ul>
            <form onSubmit={(e) => { e.preventDefault(); if (ticket.trim()) link.mutate(); }}>
              <label className="sr-only" htmlFor={`tk-${u.user_id}`}>Ticket id to link to {u.email}</label>
              <input id={`tk-${u.user_id}`} value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="Ticket id" />
              <button type="submit" className="btn btn-secondary btn-sm" disabled={!ticket.trim() || link.isPending}>Link</button>
            </form>
          </div>
        )}
      </td>
    </tr>
  );
}

function SystemStatus() {
  const { engine, agent, agentStubs } = useConnection();
  return (
    <section className="content-card" aria-labelledby="sys-title">
      <div className="app-card-header"><h2 id="sys-title">System status</h2><span className="badge">Checked every 5 seconds</span></div>
      <div className="app-card-body status-grid">
        <div><StatusDot state={engine.state} name="Data service" /><p>{engine.detail || "Checking"}</p></div>
        <div><StatusDot state={agent.state} name="Verification agent" /><p>{agent.detail || "Checking"}{agentStubs ? ". Stub tools are on, so runs return canned evidence." : ""}</p></div>
      </div>
    </section>
  );
}

export default function Admin() {
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => api.adminUsers(), retry: false });
  const pending = (users.data ?? []).filter((u) => u.status === "pending");
  return (
    <>
      <div className="page-heading"><div><h1>Administration</h1><p>Approve officer accounts, link citizens to their tickets and watch the services.</p></div><span className="badge">{pending.length} waiting for approval</span></div>
      <SystemStatus />
      <section className="content-card" aria-labelledby="users-title">
        <div className="app-card-header"><h2 id="users-title">People</h2><span className="badge">{users.data?.length ?? 0} accounts</span></div>
        {users.isPending && <div className="app-card-body"><Skeleton rows={5} label="Loading accounts" /></div>}
        {users.error && <div className="app-card-body"><ErrorState error={users.error} onRetry={() => void users.refetch()} title="We couldn't load the accounts" /></div>}
        {users.data && users.data.length === 0 && <div className="app-card-body"><EmptyState title="No accounts yet">People appear here after they register.</EmptyState></div>}
        {users.data && users.data.length > 0 && (
          <div className="table-wrap"><table>
            <thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{[...users.data].sort((a, b) => Number(b.status === "pending") - Number(a.status === "pending")).map((u) => <UserRow key={u.user_id} u={u} />)}</tbody>
          </table></div>
        )}
      </section>
    </>
  );
}
