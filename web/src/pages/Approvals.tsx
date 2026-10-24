import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../components/Toast";

export default function Approvals() {
  const qc = useQueryClient();
  const toast = useToast();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const { data, error, isLoading } = useQuery({ queryKey: ["approvals"], queryFn: () => api.approvals("pending"), refetchInterval: 2000 });
  const decide = useMutation({ mutationFn: (value: { id: string; decision: "approve" | "reject" }) => api.decide(value.id, value.decision, notes[value.id]), onSuccess: (done, v) => { void qc.invalidateQueries({ queryKey: ["approvals"] }); toast("success", v.decision === "approve" ? `Approved: ${done.action} recorded for ${done.ticket_id}.` : `Rejected: no action taken on ${done.ticket_id}.`); }, onError: () => toast("error", "The decision was not recorded. Check that the Agent is running and try again.") });
  if (isLoading) return <div className="loading-state">Loading approval queue…</div>;
  if (error) return <div className="error-state">Could not reach the Agent on :8002. ({String(error)})</div>;
  return <><div className="page-heading"><div><h1>Approval queue</h1><p>Nothing is reopened or escalated until a person approves it here.</p></div><span className="badge">{data?.length ?? 0} pending</span></div>{data?.length === 0 && <div className="empty-state"><strong>No pending approvals.</strong><p>Run the agent on a closed ticket first. Recommendations will appear here with their evidence snapshot.</p></div>}<div className="approval-list">{data?.map((approval) => <article className="app-card approval-card" key={approval.approval_id}><div className="approval-card-head"><div><Link className="table-link" to={`/ticket/${approval.ticket_id}`}>{approval.ticket_id}</Link><h2>Propose {approval.action}</h2></div><span className={`status-badge status-${approval.verdict_snapshot.state}`}><span />{approval.verdict_snapshot.state.replace(/_/g, " ")}</span></div><div className="approval-summary"><div><span className="summary-label">Posterior</span><strong>{Math.round(approval.verdict_snapshot.posterior * 100)}%</strong></div><p>{approval.verdict_snapshot.explanation}</p></div><label className="note-field"><span>Decision note <small>optional</small></span><textarea value={notes[approval.approval_id] ?? ""} onChange={(event) => setNotes((previous) => ({ ...previous, [approval.approval_id]: event.target.value }))} placeholder="Add context for the audit trail…" rows={2} /></label><div className="approval-actions"><button onClick={() => decide.mutate({ id: approval.approval_id, decision: "approve" })} disabled={decide.isPending}>Approve {approval.action} </button><button className="ghost" onClick={() => decide.mutate({ id: approval.approval_id, decision: "reject" })} disabled={decide.isPending}>Reject</button></div><small className="audit-caption">The full verdict snapshot and your note are recorded in the audit chain.</small></article>)}</div></>;
}
