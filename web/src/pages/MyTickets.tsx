import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth/AuthProvider";
import ComplaintCard from "../components/ComplaintCard";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import type { Ticket } from "../types";

const STATUS_TEXT: Record<Ticket["status"], string> = {
  open: "Still open",
  closed: "Marked as closed by the city",
  reopened: "Reopened after it was marked closed",
};

function TicketCard({ id, link = true }: { id: string; link?: boolean }) {
  const q = useQuery({ queryKey: ["my-ticket", id], queryFn: () => api.ticket(id), retry: false });
  if (q.isPending) return <article className="panel"><Skeleton rows={3} label="Loading your ticket" /></article>;
  if (q.error) return <article className="panel"><ErrorState error={q.error} onRetry={() => void q.refetch()} title={`We couldn't load ${id}`} /></article>;
  return <ComplaintCard ticket={q.data} to={link ? `/my-tickets/${encodeURIComponent(q.data.ticket_id)}` : undefined} actionLabel="View my ticket" note={STATUS_TEXT[q.data.status]} />;
}

export default function MyTickets() {
  const { me } = useAuth();
  const ids = me?.ticket_ids ?? [];
  return (
    <>
      <div className="page-heading"><div><h1>My tickets</h1><p>The complaint tickets linked to your account.</p></div></div>
      {ids.length === 0
        ? <EmptyState title="No tickets are linked to your account yet">An administrator links tickets to accounts. Once one is linked, it appears here.</EmptyState>
        : <div className="cutout-grid">{ids.map((id) => <TicketCard key={id} id={id} />)}</div>}
    </>
  );
}

/** One of the citizen's own tickets, read only. */
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
