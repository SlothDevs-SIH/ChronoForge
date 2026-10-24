import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useToast } from "../components/Toast";
import Timeline from "../components/Timeline";

const CATEGORIES = [["pothole", "Pothole"], ["garbage", "Garbage"], ["streetlight", "Street light"], ["drain", "Drain"], ["water_leak", "Water leak"], ["other", "Other"]];

function TelegramButton({ id, initial }: { id: string; initial?: string | null }) {
  const toast = useToast();
  const link = useMutation({
    mutationFn: () => api.telegramLink(id),
    onSuccess: (r) => r.telegram_link ? window.open(r.telegram_link, "_blank", "noopener") : toast("error", "Telegram is not set up on this server yet."),
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not create the Telegram link."),
  });
  if (initial) return <a className="btn btn-primary btn-sm" href={initial} target="_blank" rel="noopener noreferrer">Connect Telegram</a>;
  return <button className="btn btn-secondary btn-sm" onClick={() => link.mutate()} disabled={link.isPending}>Connect Telegram</button>;
}

function TicketRow({ id, link }: { id: string; link?: string | null }) {
  const [open, setOpen] = useState(false);
  const { data, error, isLoading } = useQuery({ queryKey: ["ticket", id], queryFn: () => api.ticket(id), retry: false, refetchInterval: 10000 });
  const note = data?.status === "reopened" ? "This request was reopened after an administrator reviewed the evidence."
    : data?.status === "closed" ? "The city marked this closed. TrueClose is checking that it was really fixed."
    : "Waiting for the city to act. You will be told here and on Telegram when it is closed.";
  return (
    <article className="app-card approval-card">
      <div className="approval-card-head"><div><strong className="table-link">{id}</strong>
        <h2>{isLoading ? "Looking up…" : error ? "Not found in the city records yet" : data?.text}</h2></div>
        {data && <span className={`status-badge status-${data.status}`}><span /> {data.status}</span>}</div>
      <small className="audit-caption">{error ? "Check the id on your receipt. Tickets from cities that are not connected yet will not appear." : note}</small>
      <div className="row-actions">
        <TelegramButton id={id} initial={link} />
        <button className="btn btn-secondary btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide history" : "Show history"}</button>
      </div>
      {open && <Timeline ticketId={id} />}
    </article>
  );
}

export default function Citizen() {
  const qc = useQueryClient();
  const toast = useToast();
  const [id, setId] = useState("");
  const [category, setCategory] = useState("pothole");
  const [text, setText] = useState("");
  const [ward, setWard] = useState("");
  const [fresh, setFresh] = useState<{ id: string; link: string | null } | null>(null);
  const [debounced, setDebounced] = useState({ category, text, ward });
  const list = useQuery({ queryKey: ["my-tickets"], queryFn: api.myTickets });

  useEffect(() => {   // look for the same problem already reported, once they stop typing
    const t = window.setTimeout(() => setDebounced({ category, text, ward }), 600);
    return () => window.clearTimeout(t);
  }, [category, text, ward]);
  const similar = useQuery({
    queryKey: ["similar", debounced],
    queryFn: () => api.similar(debounced.category, debounced.text, debounced.ward),
    enabled: debounced.text.trim().length >= 10 && debounced.ward.trim().length > 0,
    retry: false,
  });
  const mine = new Set(list.data ?? []);
  const duplicates = (similar.data ?? []).filter((s) => !mine.has(s.ticket_id));

  const add = useMutation({
    mutationFn: api.addMyTicket,
    onSuccess: (rows) => { qc.setQueryData(["my-tickets"], rows); setId(""); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not save the ticket."),
  });
  const submit = useMutation({
    mutationFn: () => api.submitRequest({ category, text, ward }),
    onSuccess: (r) => { setFresh({ id: r.ticket.ticket_id, link: r.telegram_link }); setText(""); setWard(""); void qc.invalidateQueries({ queryKey: ["my-tickets"] }); },
    onError: (e) => toast("error", e instanceof Error ? e.message : "Could not submit the request."),
  });
  const onSubmit = (e: FormEvent) => { e.preventDefault(); submit.mutate(); };
  const onAdd = (e: FormEvent) => { e.preventDefault(); if (id.trim()) add.mutate(id.trim()); };
  return (
    <>
      <div className="page-heading"><div><h1>My checks</h1><p>File a request, connect Telegram, and follow it until it is really fixed.</p></div></div>

      <form className="app-card add-ticket" onSubmit={onSubmit}>
        <h2 className="form-title">File a new request</h2>
        <label htmlFor="cat">What is the problem?</label>
        <select id="cat" value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <label htmlFor="desc">Describe it</label>
        <textarea id="desc" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Where is it and what is wrong?" />
        <label htmlFor="ward">Area or ward</label>
        <input id="ward" value={ward} onChange={(e) => setWard(e.target.value)} placeholder="e.g. Kothrud" />
        {duplicates.length > 0 && (
          <div className="dup-box" role="status">
            <strong>This may already be reported.</strong>
            {duplicates.map((d) => (
              <div key={d.ticket_id} className="dup-row"><span><b>{d.ticket_id}</b> in {d.ward} ({d.status}): {d.text}</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => add.mutate(d.ticket_id)} disabled={add.isPending}>Follow this one</button></div>
            ))}
            <small>You can still submit yours if it is a different problem.</small>
          </div>
        )}
        <button className="btn btn-primary" disabled={submit.isPending || text.trim().length < 5}>{submit.isPending ? "Submitting…" : "Submit request"}</button>
      </form>

      {fresh && (
        <div className="app-card add-ticket success-card" role="status">
          <strong>Request {fresh.id} submitted.</strong>
          <p>Connect Telegram to get a confirmation and updates. Tap the button, then press Start in the chat. In the chat you can also send a photo of the problem and TrueClose will pass it to a reviewer.</p>
          {fresh.link ? <a className="btn btn-primary" href={fresh.link} target="_blank" rel="noopener noreferrer">Connect Telegram</a>
            : <small className="muted">Telegram is not set up on this server yet.</small>}
        </div>
      )}

      <form className="app-card add-ticket" onSubmit={onAdd}>
        <label htmlFor="tid">Already have a ticket id from the city? Add it to follow it here</label>
        <div><input id="tid" value={id} onChange={(e) => setId(e.target.value)} placeholder="Ticket id" /><button className="btn btn-secondary" disabled={add.isPending || !id.trim()}>Add</button></div>
      </form>

      {list.isLoading && <div className="loading-state">Loading your tickets…</div>}
      {list.error && <div className="error-state">Could not load your tickets. ({String(list.error)})</div>}
      {list.data?.length === 0 && <div className="empty-state"><strong>No requests yet.</strong><p>File one above, or add a ticket id you already have.</p></div>}
      <div className="approval-list">{list.data?.map((t) => <TicketRow key={t} id={t} link={fresh?.id === t ? fresh.link : null} />)}</div>
    </>
  );
}
