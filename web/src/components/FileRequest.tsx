import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth/AuthProvider";
import { userMessage } from "../lib/http";
import { useToast } from "./Toast";

const CATEGORIES = [["pothole", "Pothole"], ["garbage", "Garbage"], ["streetlight", "Street light"], ["drain", "Drain"], ["water_leak", "Water leak"], ["other", "Other"]];

/** Opens the bot with a one-time link so this request's updates arrive in the citizen's Telegram chat. */
export function TelegramButton({ id, initial }: { id: string; initial?: string | null }) {
  const toast = useToast();
  const link = useMutation({
    mutationFn: () => api.telegramLink(id),
    onSuccess: (r) => r.telegram_link ? window.open(r.telegram_link, "_blank", "noopener") : toast("error", "Telegram is not set up on this server yet."),
    onError: (e) => toast("error", userMessage(e)),
  });
  if (initial) return <a className="btn btn-primary btn-sm" href={initial} target="_blank" rel="noopener noreferrer">Connect Telegram</a>;
  return <button type="button" className="btn btn-secondary btn-sm" onClick={() => link.mutate()} disabled={link.isPending}>Connect Telegram</button>;
}

/** File a new request. Looks for the same problem already reported, once the citizen stops typing. */
export default function FileRequest() {
  const { refreshProfile } = useAuth();
  const toast = useToast();
  const [category, setCategory] = useState("pothole");
  const [text, setText] = useState("");
  const [ward, setWard] = useState("");
  const [fresh, setFresh] = useState<{ id: string; link: string | null } | null>(null);
  const [debounced, setDebounced] = useState({ category, text, ward });

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced({ category, text, ward }), 600);
    return () => window.clearTimeout(t);
  }, [category, text, ward]);
  const similar = useQuery({
    queryKey: ["similar", debounced],
    queryFn: () => api.similar(debounced.category, debounced.text, debounced.ward),
    enabled: debounced.text.trim().length >= 10 && debounced.ward.trim().length > 0,
    retry: false,
  });
  const submit = useMutation({
    mutationFn: () => api.submitRequest({ category, text, ward }),
    onSuccess: (r) => { setFresh({ id: r.ticket.ticket_id, link: r.telegram_link }); setText(""); setWard(""); void refreshProfile(); },
    onError: (e) => toast("error", userMessage(e)),
  });
  const onSubmit = (e: FormEvent) => { e.preventDefault(); submit.mutate(); };
  const duplicates = similar.data ?? [];

  return (
    <>
      <form className="panel file-request" onSubmit={onSubmit}>
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
            <span>{duplicates.length === 1 ? "Someone has already reported a similar problem" : `${duplicates.length} similar problems are already reported`} in {duplicates[0].ward} and {duplicates.length === 1 ? "is" : "are"} still open. You can still send yours if it is a different problem.</span>
          </div>
        )}
        <button type="submit" className="btn btn-primary" disabled={submit.isPending || text.trim().length < 5}>{submit.isPending ? "Submitting…" : "Submit request"}</button>
      </form>
      {fresh && (
        <div className="panel success-card" role="status">
          <strong>Request {fresh.id} submitted.</strong>
          <p>Connect Telegram to get a confirmation and updates. Tap the button, then press Start in the chat. In the chat you can also send a photo of the problem and TrueClose will pass it to a reviewer.</p>
          {fresh.link ? <a className="btn btn-primary" href={fresh.link} target="_blank" rel="noopener noreferrer">Connect Telegram</a>
            : <small className="muted">Telegram is not set up on this server yet.</small>}
        </div>
      )}
    </>
  );
}
