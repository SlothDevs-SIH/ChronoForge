import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { TraceEvent } from "../types";

export default function TicketDetail() {
  const { id = "" } = useParams();
  const { data: ticket } = useQuery({ queryKey: ["ticket", id], queryFn: () => api.ticket(id), refetchInterval: 3000 });
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const close = useRef<() => void>();
  useEffect(() => () => close.current?.(), []);

  async function run() {
    setEvents([]);
    setRunning(true);
    const { run_id } = await api.startRun(id);
    close.current = api.streamRun(run_id, (e) => setEvents((prev) => [...prev, e]), () => setRunning(false));
  }

  const last = events[events.length - 1];
  if (!ticket) return <p>Loading...</p>;
  return (
    <>
      <h1>{ticket.ticket_id}</h1>
      <div className="cols">
        <section className="card">
          <h2>Ticket</h2>
          <p>{ticket.text}</p>
          <p>{ticket.category} - {ticket.ward}, {ticket.city} <span className={`badge ${ticket.data_quality}`}>{ticket.data_quality}</span></p>
          <p>Status: <strong>{ticket.status}</strong></p>
          <p>Closure note: {ticket.closure_note ?? "(none)"}</p>
        </section>
        <section className="card">
          <h2>Agent trace</h2>
          <button onClick={run} disabled={running}>{running ? "Running..." : "Run agent"}</button>
          {last && <p>Budget left: {last.budget_left}</p>}
          <ol className="trace">
            {events.map((e) => (
              <li key={e.step}><strong>{e.tool ?? e.type}</strong>: {e.summary}</li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}
