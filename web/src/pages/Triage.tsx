import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Score } from "../types";

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

export default function Triage({ city }: { city: string }) {
  const { data, error, isLoading } = useQuery({ queryKey: ["tickets", city], queryFn: () => api.tickets(city || undefined, "closed", 100, "risk") });
  if (isLoading) return <p>Loading tickets...</p>;
  if (error) return <p>Could not reach the Engine on :8001. Is it running? ({String(error)})</p>;
  return (
    <>
      <h1>Triage queue</h1>
      <p>Closed tickets ranked by risk. For real cities this is a rank, not a probability: see the score type.</p>
      <table>
        <thead>
          <tr><th>Ticket</th><th>City</th><th>Ward</th><th>Category</th><th>Risk</th><th>Score type</th></tr>
        </thead>
        <tbody>
          {data!.map(({ ticket, score }) => (
            <tr key={ticket.ticket_id}>
              <td><Link to={`/ticket/${ticket.ticket_id}`}>{ticket.ticket_id}</Link></td>
              <td>{ticket.city} <span className={`badge ${ticket.data_quality}`}>{ticket.data_quality}</span></td>
              <td>{ticket.ward}</td>
              <td>{ticket.category}</td>
              <td>{riskCell(score).text}</td>
              <td><span className="badge">{score.score_type.replace(/_/g, " ")}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
