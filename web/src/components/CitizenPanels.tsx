// Officer-side panels on the ticket page: ask the citizen (reply link) and look at what they sent (stored photos).
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { userMessage } from "../lib/http";
import type { CitizenPhoto } from "../types";
import { ErrorState, Skeleton } from "./States";
import { useToast } from "./Toast";

const LANGS: [string, string][] = [["en", "English"], ["hi", "Hindi"], ["mr", "Marathi"], ["kn", "Kannada"]];

export function ReplyLinkPanel({ ticketId }: { ticketId: string }) {
  const toast = useToast();
  const [lang, setLang] = useState("en");
  const create = useMutation({
    mutationFn: () => api.replyLink(ticketId, lang),
    onError: (e) => toast("error", userMessage(e)),
  });
  const link = create.data ? `${window.location.origin}/reply/${create.data.token}` : "";
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      toast("success", "Link copied.");
    } catch {
      toast("error", "Couldn't copy. Select the link and copy it by hand.");
    }
  }
  return (
    <section className="app-card reply-link-card">
      <div className="app-card-header"><div><h2>Ask the citizen</h2><small className="header-caption">One link per ticket, answered with yes, partly or no</small></div></div>
      <div className="app-card-body reply-link-body">
        <label className="field-inline"><span>Language</span>
          <select value={lang} onChange={(e) => { setLang(e.target.value); create.reset(); }}>
            {LANGS.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
          </select>
        </label>
        <button type="button" className="btn btn-secondary" onClick={() => create.mutate()} disabled={create.isPending}>{create.isPending ? "Creating link…" : "Create reply link"}</button>
        {create.data && (
          <div className="reply-link-result">
            <input readOnly value={link} aria-label="Citizen reply link" onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copy()}>Copy</button>
            <small>Expires {new Date(create.data.expires_at).toLocaleDateString()}. Send it to the citizen yourself; nothing is sent from here.</small>
          </div>
        )}
      </div>
    </section>
  );
}

function PhotoRow({ photo }: { photo: CitizenPhoto }) {
  const toast = useToast();
  const [url, setUrl] = useState("");
  const show = useMutation({ mutationFn: () => api.evidenceUrl(photo.evidence_id), onSuccess: setUrl, onError: (e) => toast("error", userMessage(e)) });
  return (
    <li className="citizen-photo">
      <div>
        <strong>{new Date(photo.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</strong>
        <small>{photo.content_type.replace("image/", "").toUpperCase()}, {(photo.size_bytes / 1024).toFixed(0)} KB, fingerprint {photo.sha256.slice(0, 8)}</small>
      </div>
      {url
        ? <img src={url} alt="Photo sent by the citizen" />
        : <button type="button" className="btn btn-secondary btn-sm" onClick={() => show.mutate()} disabled={show.isPending}>{show.isPending ? "Opening…" : "Show photo"}</button>}
    </li>
  );
}

export function CitizenPhotos({ ticketId }: { ticketId: string }) {
  const q = useQuery({ queryKey: ["evidence", ticketId], queryFn: () => api.ticketEvidence(ticketId), retry: false });
  return (
    <section className="app-card citizen-photos-card">
      <div className="app-card-header"><div><h2>Citizen photos</h2><small className="header-caption">Stored for review, never counted as proof</small></div></div>
      <div className="app-card-body">
        {q.isPending ? <Skeleton rows={2} label="Loading citizen photos" />
          : q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="We couldn't load the citizen photos" />
          : q.data.length === 0 ? <p className="muted">No citizen has sent a photo for this ticket.</p>
          : <ul className="citizen-photo-list">{q.data.map((p) => <PhotoRow key={p.evidence_id} photo={p} />)}</ul>}
      </div>
    </section>
  );
}
