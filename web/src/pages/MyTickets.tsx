import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth/AuthProvider";
import ComplaintCard from "../components/ComplaintCard";
import FileRequest, { TelegramButton } from "../components/FileRequest";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import Timeline from "../components/Timeline";
import type { Ticket } from "../types";

const STATUS_TEXT: Record<Ticket["status"], string> = {
  open: "Still open",
  closed: "Marked as closed by the city",
  reopened: "Reopened after it was marked closed",
};

function TicketCard({ id, link = true }: { id: string; link?: boolean }) {
  const q = useQuery({ queryKey: ["my-ticket", id], queryFn: () => api.ticket(id), retry: false, refetchInterval: 10000 });
  const [history, setHistory] = useState(false);
  if (q.isPending) return <article className="panel"><Skeleton rows={3} label="Loading your ticket" /></article>;
  if (q.error) return <article className="panel"><ErrorState error={q.error} onRetry={() => void q.refetch()} title={`We couldn't load ${id}`} /></article>;
  return (
    <div className="ticket-with-history">
      <ComplaintCard ticket={q.data} to={link ? `/my-tickets/${encodeURIComponent(q.data.ticket_id)}` : undefined} actionLabel="View my ticket" note={STATUS_TEXT[q.data.status]} />
      <div className="row-actions">
        <TelegramButton id={id} />
        <button type="button" className="btn btn-secondary btn-sm" aria-expanded={history} onClick={() => setHistory(!history)}>{history ? "Hide history" : "Show history"}</button>
      </div>
      {history && <Timeline ticketId={id} />}
    </div>
  );
}

export default function MyTickets() {
  const { me, status } = useAuth();
  const ids = me?.ticket_ids ?? [];
  const canFile = me?.role === "citizen" || status === "disabled";
  return (
    <>
      <div className="page-heading"><div><h1>My tickets</h1><p>File a request, connect Telegram, and follow it until it is really fixed.</p></div></div>
      {canFile && <FileRequest />}
      {ids.length === 0
        ? <EmptyState title="No tickets yet">File a request above. Tickets an administrator links to your account also appear here.</EmptyState>
        : <div className="cutout-grid">{ids.map((id) => <TicketCard key={id} id={id} />)}</div>}
    </>
  );
}

/** One of the citizen's own tickets, read only, with its history. */
export function MyTicket() {
  const { id = "" } = useParams();
  const { me } = useAuth();
  const mine = me?.ticket_ids.includes(id);
  return (
    <>
      <div className="breadcrumb"><Link to="/my-tickets">My tickets</Link><span>/</span><strong>{id}</strong></div>
      {mine ? <div className="cutout-grid"><TicketCard id={id} link={false} /></div> : <ErrorState error={new Error("not linked")} title="This ticket isn't linked to your account" />}
    </>
  );
}
