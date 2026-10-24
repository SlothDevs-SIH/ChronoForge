import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Triage({ city }: { city: string }) {
  const { data, error, isLoading } = useQuery({ queryKey: ["tickets", city], queryFn: () => api.tickets(city || undefined) });
  if (isLoading) return <p>Loading tickets...</p>;
  if (error) return <p>Could not reach the Engine on :8001. Is it running? ({String(error)})</p>;
  return (
    <>
      <h1>Triage queue</h1>
      <p>Closed tickets ranked by probability of a false closure.</p>
      <table>
        <thead>
          <tr><th>Ticket</th><th>City</th><th>Ward</th><th>Category</th><th className="num">P(false closure)</th><th>Top reason</th></tr>
        </thead>
        <tbody>
          {data!.map(({ ticket, score }) => (
            <tr key={ticket.ticket_id}>
              <td><Link to={`/ticket/${ticket.ticket_id}`}>{ticket.ticket_id}</Link></td>
              <td>{ticket.city} <span className={`badge ${ticket.data_quality}`}>{ticket.data_quality}</span></td>
              <td>{ticket.ward}</td>
              <td>{ticket.category}</td>
              <td className="num">{(score.p_false_closure * 100).toFixed(0)}%</td>
              <td>{score.reasons[0]?.feature ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
