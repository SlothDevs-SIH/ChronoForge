import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { TimelineEvent } from "../types";

const when = (ts: string) => {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

/** The case history, newest last. `staff` also shows internal entries (decisions, delivery problems). */
export default function Timeline({ ticketId, staff = false }: { ticketId: string; staff?: boolean }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["timeline", staff ? "staff" : "me", ticketId],
    queryFn: () => (staff ? api.caseTimeline(ticketId) : api.myTimeline(ticketId)),
    refetchInterval: 8000,
    retry: false,
  });
  if (isLoading) return <p className="muted">Loading history…</p>;
  if (error) return <p className="muted">History is not available right now.</p>;
  if (!data?.length) return <p className="muted">Nothing has happened on this case yet.</p>;
  return (
    <ol className="timeline">
      {data.map((e: TimelineEvent, i) => (
        <li key={i} className={e.audience === "staff" ? "is-staff" : ""}>
          <time dateTime={e.ts}>{when(e.ts)}</time>
          <span>{e.text}{e.audience === "staff" && <small> · staff only</small>}</span>
        </li>
      ))}
    </ol>
  );
}
