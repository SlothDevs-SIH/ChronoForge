import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { TimelineEvent } from "../types";

const when = (ts: string) => {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

/** The case history, newest last. The server decides what the viewer may see: staff also get internal entries. */
export default function Timeline({ ticketId }: { ticketId: string }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["timeline", ticketId],
    queryFn: () => api.caseTimeline(ticketId),
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
