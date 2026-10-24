import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { userMessage } from "../lib/http";
import type { Approval } from "../types";
import { useToast } from "./Toast";

/** Plain-language reasons behind a recommendation, built by the Agent only from the evidence it recorded. */
export function Reasons({ approval }: { approval: Approval }) {
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

/** Approved actions the city system did not carry out, with a Retry. Hidden when there are none. */
export function RetryPanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({ queryKey: ["approvals", "approved"], queryFn: () => api.approvals("approved"), refetchInterval: 5000, retry: false });
  const retry = useMutation({
    mutationFn: api.retryApproval,
    onSuccess: (a) => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      toast(a.engine_result?.ok ? "success" : "error", a.engine_result?.ok ? `Done: ${a.ticket_id} was ${a.action === "reopen" ? "reopened" : "escalated"}.` : "The city system still did not act.");
    },
    onError: (e) => toast("error", userMessage(e)),
  });
  const failed = (data ?? []).filter((a) => a.engine_result && !a.engine_result.ok);
  if (!failed.length) return null;
  return (
    <section className="app-card retry-card">
      <div className="app-card-header"><h2>Approved, but the city system did not act</h2><span className="badge">{failed.length}</span></div>
      <div className="app-card-body">
        {failed.map((a) => (
          <div key={a.approval_id} className="dup-row"><span><Link className="table-link" to={`/ticket/${a.ticket_id}`}>{a.ticket_id}</Link>: {a.action} approved but not carried out.</span>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => retry.mutate(a.approval_id)} disabled={retry.isPending}>Retry</button></div>
        ))}
      </div>
    </section>
  );
}
