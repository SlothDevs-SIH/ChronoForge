import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../components/Toast";
import type { Approval } from "../types";

function Reasons({ approval }: { approval: Approval }) {
  const x = approval.explain;
  if (!x) return null;
  return (
    <div className="reasons">
      <p className="reasons-summary">{x.summary}</p>
      {x.against.length > 0 && <><h3>Why it looks like a false closure</h3><ul className="reasons-against">{x.against.map((l) => <li key={l}>{l}</li>)}</ul></>}
      {x.for.length > 0 && <><h3>What points the other way</h3><ul className="reasons-for">{x.for.map((l) => <li key={l}>{l}</li>)}</ul></>}
      {x.unknown.length > 0 && <><h3>Could not be checked</h3><ul className="reasons-unknown">{x.unknown.map((l) => <li key={l}>{l}</li>)}</ul></>}
    </div>
  );
}

function Retry() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({ queryKey: ["approvals", "approved"], queryFn: () => api.approvals("approved"), refetchInterval: 5000 });
  const retry = useMutation({
    mutationFn: api.retryApproval,
    onSuccess: (a) => { void qc.invalidateQueries({ queryKey: ["approvals"] }); toast(a.engine_result?.ok ? "success" : "error", a.engine_result?.ok ? `Done: ${a.ticket_id} was ${a.action === "reopen" ? "reopened" : "escalated"}.` : "The city system still did not act."); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not retry."),
  });
  const failed = (data ?? []).filter((a) => a.engine_result && !a.engine_result.ok);
  if (!failed.length) return null;
  return (
    <section className="app-card retry-card">
      <div className="app-card-header"><h2>Approved, but the city system did not act</h2><span className="badge">{failed.length}</span></div>
      <div className="app-card-body">
        {failed.map((a) => (
          <div key={a.approval_id} className="dup-row"><span><Link className="table-link" to={`/ticket/${a.ticket_id}`}>{a.ticket_id}</Link>: {a.action} approved but not carried out.</span>
            <button className="btn btn-primary btn-sm" onClick={() => retry.mutate(a.approval_id)} disabled={retry.isPending}>Retry</button></div>
        ))}
      </div>
    </section>
  );
}

export default function Approvals() {
  const qc = useQueryClient();
  const toast = useToast();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const { data, error, isLoading } = useQuery({ queryKey: ["approvals", "pending"], queryFn: () => api.approvals("pending"), refetchInterval: 2000 });
  const decide = useMutation({
    mutationFn: (v: { id: string; decision: "approve" | "reject" }) => api.decide(v.id, v.decision, notes[v.id]),
    onSuccess: (done, v) => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      toast("success", v.decision === "approve" ? `Approved: ${done.action} recorded for ${done.ticket_id}.` : `Rejected: no action taken on ${done.ticket_id}.`);
    },
    onError: (e) => toast("error", e instanceof Error ? e.message : "The decision was not recorded. Check that the Agent is running and try again."),
  });
  if (isLoading) return <div className="loading-state">Loading approval queue…</div>;
  if (error) return <div className="error-state">Could not load approvals. Check that you are signed in and the Agent is running. ({String(error)})</div>;
  return (
    <>
      <div className="page-heading"><div><h1>Approval queue</h1><p>Nothing is reopened or escalated until a person approves it here.</p></div><span className="badge">{data?.length ?? 0} pending</span></div>
      <Retry />
      {data?.length === 0 && <div className="empty-state"><strong>No pending approvals.</strong><p>When a closed request looks falsely closed, or a citizen has not answered, it appears here with the reasons.</p></div>}
      <div className="approval-list">
        {data?.map((approval) => (
          <article className="app-card approval-card" key={approval.approval_id}>
            <div className="approval-card-head">
              <div><Link className="table-link" to={`/ticket/${approval.ticket_id}`}>{approval.ticket_id}</Link>
                <h2>{approval.action === "reopen" ? "This request needs reopening" : "This request needs a person to look at it"}</h2></div>
              <span className={`status-badge status-${approval.verdict_snapshot.state}`}><span />{approval.verdict_snapshot.state.replace(/_/g, " ")}</span>
            </div>
            <div className="approval-summary"><div><span className="summary-label">Posterior</span><strong>{Math.round(approval.verdict_snapshot.posterior * 100)}%</strong></div><p>{approval.verdict_snapshot.explanation}</p></div>
            <Reasons approval={approval} />
            <label className="note-field"><span>Decision note <small>optional</small></span>
              <textarea value={notes[approval.approval_id] ?? ""} onChange={(e) => setNotes((p) => ({ ...p, [approval.approval_id]: e.target.value }))} placeholder="Add context for the audit trail…" rows={2} /></label>
            <div className="approval-actions">
              <button onClick={() => decide.mutate({ id: approval.approval_id, decision: "approve" })} disabled={decide.isPending}>{approval.action === "reopen" ? "Reopen this request" : "Escalate"}</button>
              <button className="ghost" onClick={() => decide.mutate({ id: approval.approval_id, decision: "reject" })} disabled={decide.isPending}>Reject</button>
            </div>
            <small className="audit-caption">The full verdict snapshot and your note are recorded in the audit chain.</small>
          </article>
        ))}
      </div>
    </>
  );
}
