import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Reasons, RetryPanel } from "../components/ApprovalExtras";
import ComplaintCard from "../components/ComplaintCard";
import { useToast } from "../components/Toast";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { userMessage } from "../lib/http";

// The ticket behind an approval, so the reviewer sees its photo (if it has one) and record. If it can't be loaded the approval still works.
function ApprovalTicket({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["my-ticket", id], queryFn: () => api.ticket(id), retry: false });
  if (!q.data) return null;
  return <div className="approval-ticket"><ComplaintCard ticket={q.data} to={`/ticket/${q.data.ticket_id}`} showSummary={false} /></div>;
}

export default function Approvals() {
  const qc = useQueryClient();
  const toast = useToast();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ["approvals"], queryFn: () => api.approvals("pending"), refetchInterval: 4000, retry: false });
  const decide = useMutation({ mutationFn: (value: { id: string; decision: "approve" | "reject" }) => api.decide(value.id, value.decision, notes[value.id]), onSuccess: (done, v) => { void qc.invalidateQueries({ queryKey: ["approvals"] }); toast("success", v.decision === "approve" ? `Approved: ${done.action} recorded for ${done.ticket_id}.` : `Rejected: no action taken on ${done.ticket_id}.`); }, onError: (e) => toast("error", `The decision was not recorded. ${userMessage(e)}`) });
  if (isLoading) return <Skeleton rows={4} label="Loading the approval queue" />;
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} title="We couldn't load the approval queue" />;
  return <><div className="page-heading"><div><h1>Approval queue</h1><p>Nothing is reopened or escalated until a person approves it here.</p></div><span className="badge">{data?.length ?? 0} pending</span></div><RetryPanel />{data?.length === 0 && <EmptyState title="No pending approvals">Run the agent on a closed ticket first. Recommendations appear here with their evidence snapshot.</EmptyState>}<div className="approval-list">{data?.map((approval) => <article className="app-card approval-card" key={approval.approval_id}><div className="approval-card-head"><div><Link className="table-link" to={`/ticket/${approval.ticket_id}`}>{approval.ticket_id}</Link><h2>{approval.action === "reopen" ? "This request needs reopening" : "This request needs a person to look at it"}</h2></div><span className={`status-badge status-${approval.verdict_snapshot.state}`}><span />{approval.verdict_snapshot.state.replace(/_/g, " ")}</span></div><ApprovalTicket id={approval.ticket_id} /><div className="approval-summary"><div><span className="summary-label">Posterior</span><strong>{Math.round(approval.verdict_snapshot.posterior * 100)}%</strong></div><p>{approval.verdict_snapshot.explanation}</p></div><Reasons approval={approval} /><label className="note-field"><span>Decision note <small>optional</small></span><textarea value={notes[approval.approval_id] ?? ""} onChange={(event) => setNotes((previous) => ({ ...previous, [approval.approval_id]: event.target.value }))} placeholder="Add context for the audit trail…" rows={2} /></label><div className="approval-actions"><button onClick={() => decide.mutate({ id: approval.approval_id, decision: "approve" })} disabled={decide.isPending}>{approval.action === "reopen" ? "Reopen this request" : "Escalate"}</button><button className="ghost" onClick={() => decide.mutate({ id: approval.approval_id, decision: "reject" })} disabled={decide.isPending}>Reject</button></div><small className="audit-caption">The full verdict snapshot and your note are recorded in the audit chain.</small></article>)}</div></>;
}
