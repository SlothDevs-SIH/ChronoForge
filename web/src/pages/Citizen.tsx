import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useToast } from "../components/Toast";

function TicketRow({ id }: { id: string }) {
  const { data, error, isLoading } = useQuery({ queryKey: ["ticket", id], queryFn: () => api.ticket(id), retry: false });
  return (
    <article className="app-card approval-card">
      <div className="approval-card-head"><div><strong className="table-link">{id}</strong>
        <h2>{isLoading ? "Looking up…" : error ? "Not found in the city records yet" : data?.text}</h2></div>
        {data && <span className={`status-badge status-${data.status}`}><span /> {data.status}</span>}</div>
      <small className="audit-caption">{error ? "Check the id on your receipt. Tickets from cities that are not connected yet will not appear." : "TrueClose checks closed tickets independently. You may be asked to confirm the repair through the Telegram bot."}</small>
    </article>
  );
}

export default function Citizen() {
  const qc = useQueryClient();
  const toast = useToast();
  const [id, setId] = useState("");
  const list = useQuery({ queryKey: ["my-tickets"], queryFn: api.myTickets });
  const add = useMutation({
    mutationFn: api.addMyTicket,
    onSuccess: (rows) => { qc.setQueryData(["my-tickets"], rows); setId(""); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not save the ticket."),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (id.trim()) add.mutate(id.trim()); };
  return (
    <>
      <div className="page-heading"><div><h1>My checks</h1><p>Follow the complaints you filed and see whether the repair has been independently checked.</p></div></div>
      <form className="app-card add-ticket" onSubmit={submit}>
        <label htmlFor="tid">Ticket id from your complaint receipt</label>
        <div><input id="tid" value={id} onChange={(e) => setId(e.target.value)} placeholder="Ticket id" /><button className="btn btn-primary" disabled={add.isPending || !id.trim()}>Add</button></div>
      </form>
      {list.isLoading && <div className="loading-state">Loading your tickets…</div>}
      {list.error && <div className="error-state">Could not load your tickets. ({String(list.error)})</div>}
      {list.data?.length === 0 && <div className="empty-state"><strong>No tickets yet.</strong><p>Add the id of a complaint you filed to follow it here.</p></div>}
      <div className="approval-list">{list.data?.map((t) => <TicketRow key={t} id={t} />)}</div>
    </>
  );
}
