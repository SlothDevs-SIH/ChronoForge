import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Approvals() {
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["approvals"], queryFn: () => api.approvals("pending"), refetchInterval: 2000 });
  const decide = useMutation({
    mutationFn: (v: { id: string; decision: "approve" | "reject" }) => api.decide(v.id, v.decision),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
  if (error) return <p>Could not reach the Agent on :8002. ({String(error)})</p>;
  return (
    <>
      <h1>Approval queue</h1>
      <p>Nothing is reopened or escalated until a person approves it here.</p>
      {data?.length === 0 && <p>No pending approvals. Run the agent on a ticket first.</p>}
      {data?.map((a) => (
        <div className="card" key={a.approval_id} style={{ marginBottom: "1rem" }}>
          <h3><Link to={`/ticket/${a.ticket_id}`}>{a.ticket_id}</Link>: propose {a.action}</h3>
          <p className={`verdict-${a.verdict_snapshot.state}`}>
            {a.verdict_snapshot.state.replace(/_/g, " ")} (posterior {a.verdict_snapshot.posterior.toFixed(2)})
          </p>
          <p>{a.verdict_snapshot.explanation}</p>
          <button onClick={() => decide.mutate({ id: a.approval_id, decision: "approve" })}>Approve {a.action}</button>{" "}
          <button className="ghost" onClick={() => decide.mutate({ id: a.approval_id, decision: "reject" })}>Reject</button>
        </div>
      ))}
    </>
  );
}
