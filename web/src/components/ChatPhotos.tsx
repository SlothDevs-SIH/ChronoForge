import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** Photos a citizen sent in the Telegram chat. For a person to judge: they never change the score. */
export default function ChatPhotos({ ticketId }: { ticketId: string }) {
  const { data } = useQuery({ queryKey: ["chat-photos", ticketId], queryFn: () => api.casePhotos(ticketId), retry: false, refetchInterval: 10000 });
  if (!data?.length) return null;
  return (
    <section className="app-card">
      <div className="app-card-header"><div><h2>Photos sent in the chat</h2><small className="header-caption">For a person to judge. They never change the score.</small></div><span className="badge">{data.length}</span></div>
      <div className="app-card-body photo-strip">
        {data.map((p) => (
          <figure key={p.photo_id}><img src={p.data_url} alt="Photo sent by the citizen" loading="lazy" />
            <figcaption>{new Date(p.received_at).toLocaleString()}{p.details.flags?.length ? <strong className="photo-flag"> Flagged: {p.details.flags.join("; ")}</strong> : null}</figcaption></figure>
        ))}
      </div>
    </section>
  );
}
