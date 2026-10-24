// The only place that calls fetch. Components import from here.
import type { Approval, CitySummary, Ticket, TicketWithScore, TraceEvent, WardStat } from "./types";

const ENGINE = "/api/engine";
const AGENT = "/api/agent";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  tickets: (city?: string, status?: string, limit = 100, sort: "newest" | "risk" = "newest") => {
    const q = new URLSearchParams({ limit: String(limit), sort });
    if (city) q.set("city", city);
    if (status) q.set("status", status);
    return fetch(`${ENGINE}/tickets?${q}`).then((r) => json<TicketWithScore[]>(r));
  },
  cities: () => fetch(`${ENGINE}/cities`).then((r) => json<CitySummary[]>(r)),
  ticket: (id: string) => fetch(`${ENGINE}/tickets/${id}`).then((r) => json<Ticket>(r)),
  wardStats: (city?: string) =>
    fetch(`${ENGINE}/wards/stats${city ? `?city=${city}` : ""}`).then((r) => json<WardStat[]>(r)),
  startRun: (id: string) =>
    fetch(`${AGENT}/agent/run/${id}`, { method: "POST" }).then((r) => json<{ run_id: string }>(r)),
  approvals: (status?: string) =>
    fetch(`${AGENT}/approvals${status ? `?status=${status}` : ""}`).then((r) => json<Approval[]>(r)),
  decide: (id: string, decision: "approve" | "reject", note?: string) =>
    fetch(`${AGENT}/approvals/${id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note }),
    }).then((r) => json<Approval>(r)),
  /** Subscribe to the live agent trace. Returns a close function. */
  streamRun(runId: string, onEvent: (e: TraceEvent) => void, onEnd: () => void): () => void {
    const es = new EventSource(`${AGENT}/agent/stream/${runId}`);
    es.onmessage = (m) => onEvent(JSON.parse(m.data) as TraceEvent);
    es.addEventListener("end", () => { es.close(); onEnd(); });
    es.onerror = () => { es.close(); onEnd(); };
    return () => es.close();
  },
};
