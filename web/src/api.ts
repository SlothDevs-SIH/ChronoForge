// The only place that calls fetch. Components import from here.
import type { Approval, WardDot, AuditEntry, CitySummary, Evidence, Score, Ticket, TicketWithScore, TraceEvent, WardStat } from "./types";

const ENGINE = "/api/engine";
const AGENT = "/api/agent";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  evalResults: () => fetch(`${ENGINE}/eval/results`).then((r) => json<Record<string, unknown>>(r)),
  audit: () => fetch(`${AGENT}/audit`).then((r) => json<AuditEntry[]>(r)),
  auditVerify: () => fetch(`${AGENT}/audit/verify`).then((r) => json<{ ok: boolean; first_broken_idx: number | null; length: number }>(r)),
  wardMap: (city: string) => fetch(`${ENGINE}/wards/map?city=${encodeURIComponent(city)}`).then((r) => json<WardDot[]>(r)),
  engineHealth: () => fetch(`${ENGINE}/health`).then((r) => json<{ ok: boolean; mode: string }>(r)),
  agentHealth: () => fetch(`${AGENT}/health`).then((r) => json<{ ok: boolean; stubs: boolean }>(r)),
  /** Demo set photos, served by the Engine (open-licence images, see demo/photos/ATTRIBUTION.md). */
  demoPhoto: (ticketId: string, which: "before" | "after") => `${ENGINE}/media/demo/${ticketId}/${which}.jpg`,
  satelliteChip: (ticketId: string, which: "before" | "after") => `${ENGINE}/satellite/chip/${ticketId}/${which}.png`,
  satelliteCheck: (ticketId: string, cachedOnly = true) =>
    fetch(`${ENGINE}/satellite/check`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket_id: ticketId, cached_only: cachedOnly }) }).then((r) => json<Evidence>(r)),
  tickets: (city?: string, status?: string, limit = 100, sort: "newest" | "risk" = "newest") => {
    const q = new URLSearchParams({ limit: String(limit), sort });
    if (city) q.set("city", city);
    if (status) q.set("status", status);
    return fetch(`${ENGINE}/tickets?${q}`).then((r) => json<TicketWithScore[]>(r));
  },
  cities: () => fetch(`${ENGINE}/cities`).then((r) => json<CitySummary[]>(r)),
  ticket: (id: string) => fetch(`${ENGINE}/tickets/${id}`).then((r) => json<Ticket>(r)),
  score: (id: string) => fetch(`${ENGINE}/tickets/${id}/score`).then((r) => json<Score>(r)),
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
    // The Agent service sends NAMED events ("event: trace"); an unnamed listener would never fire for them.
    // Listen to both, so either server behaviour works.
    const handle = (m: MessageEvent) => {
      try {
        const e = JSON.parse(m.data);
        if (e && typeof e.step === "number") onEvent(e as TraceEvent);   // ignore keep-alives and the end marker
      } catch { /* not JSON: a comment or ping */ }
    };
    es.onmessage = handle;
    es.addEventListener("trace", handle as EventListener);
    es.addEventListener("end", () => { es.close(); onEnd(); });
    es.onerror = () => { es.close(); onEnd(); };
    return () => es.close();
  },
};
