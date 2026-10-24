// The only place that calls fetch. Components import from here.
import type { CasePhoto, Hotspot, SimilarRequest, Summary, TimelineEvent, Approval, WardDot, AuditEntry, CitySummary, Evidence, Score, Ticket, TicketWithScore, TraceEvent, WardStat } from "./types";

const ENGINE = "/api/engine";
const AGENT = "/api/agent";

export type Role = "citizen" | "officer" | "admin";
export interface User { user_id: string; email: string; name: string; role: Role; status: "active" | "pending" | "disabled" }

const KEY = "trueclose.token";
export const session = {
  get: () => { try { return localStorage.getItem(KEY); } catch { return null; } },
  set: (t: string) => { try { localStorage.setItem(KEY, t); } catch { /* storage blocked: session lasts until reload */ } },
  clear: () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } },
};

/** fetch that sends the session token. A 401 means the session ended, so the app is told to return to sign-in. */
function afetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = session.get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers }).then((res) => {
    if (res.status === 401 && token) { session.clear(); window.dispatchEvent(new Event("trueclose:signed-out")); }
    return res;
  });
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { const body = await res.json(); if (typeof body?.detail === "string") detail = body.detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const post = (url: string, body: unknown) => afetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  register: (email: string, name: string, password: string, role: "citizen" | "officer") => post(`${AGENT}/auth/register`, { email, name, password, role }).then((r) => json<User>(r)),
  login: (email: string, password: string) => post(`${AGENT}/auth/login`, { email, password }).then((r) => json<{ token: string; user: User }>(r)),
  me: () => afetch(`${AGENT}/auth/me`).then((r) => json<User>(r)),
  users: () => afetch(`${AGENT}/admin/users`).then((r) => json<User[]>(r)),
  setUserStatus: (id: string, status: "active" | "disabled") => post(`${AGENT}/admin/users/${id}/status`, { status }).then((r) => json<User>(r)),
  submitRequest: (body: { category: string; text: string; ward: string }) => post(`${AGENT}/me/requests`, body).then((r) => json<{ ticket: Ticket; telegram_link: string | null; linked: boolean }>(r)),
  telegramLink: (id: string) => post(`${AGENT}/me/requests/${encodeURIComponent(id)}/telegram-link`, {}).then((r) => json<{ telegram_link: string | null; linked: boolean }>(r)),
  closeRequest: (id: string) => post(`${AGENT}/admin/requests/${encodeURIComponent(id)}/close`, {}).then((r) => json<{ ticket_id: string; status: string }>(r)),
  myTimeline: (id: string) => afetch(`${AGENT}/me/requests/${encodeURIComponent(id)}/timeline`).then((r) => json<TimelineEvent[]>(r)),
  caseTimeline: (id: string) => afetch(`${AGENT}/cases/${encodeURIComponent(id)}/timeline`).then((r) => json<TimelineEvent[]>(r)),
  casePhotos: (id: string) => afetch(`${AGENT}/cases/${encodeURIComponent(id)}/photos`).then((r) => json<CasePhoto[]>(r)),
  similar: (category: string, text: string, ward: string) => afetch(`${AGENT}/me/requests/similar?${new URLSearchParams({ category, text, ward })}`).then((r) => json<SimilarRequest[]>(r)),
  summary: (days: number) => afetch(`${AGENT}/admin/summary?days=${days}`).then((r) => json<Summary>(r)),
  retryApproval: (id: string) => post(`${AGENT}/approvals/${id}/retry`, {}).then((r) => json<Approval>(r)),
  hotspots: () => afetch(`${ENGINE}/insights/hotspots`).then((r) => json<{ rule: string; caveat: string; hotspots: Hotspot[] }>(r)),
  myTickets: () => afetch(`${AGENT}/me/tickets`).then((r) => json<string[]>(r)),
  addMyTicket: (ticket_id: string) => post(`${AGENT}/me/tickets`, { ticket_id }).then((r) => json<string[]>(r)),
  evalResults: () => afetch(`${ENGINE}/eval/results`).then((r) => json<Record<string, unknown>>(r)),
  audit: () => afetch(`${AGENT}/audit`).then((r) => json<AuditEntry[]>(r)),
  auditVerify: () => afetch(`${AGENT}/audit/verify`).then((r) => json<{ ok: boolean; first_broken_idx: number | null; length: number }>(r)),
  wardMap: (city: string) => afetch(`${ENGINE}/wards/map?city=${encodeURIComponent(city)}`).then((r) => json<WardDot[]>(r)),
  engineHealth: () => afetch(`${ENGINE}/health`).then((r) => json<{ ok: boolean; mode: string }>(r)),
  agentHealth: () => afetch(`${AGENT}/health`).then((r) => json<{ ok: boolean; stubs: boolean }>(r)),
  /** Demo set photos, served by the Engine (open-licence images, see demo/photos/ATTRIBUTION.md). */
  demoPhoto: (ticketId: string, which: "before" | "after") => `${ENGINE}/media/demo/${ticketId}/${which}.jpg`,
  satelliteChip: (ticketId: string, which: "before" | "after") => `${ENGINE}/satellite/chip/${ticketId}/${which}.png`,
  satelliteCheck: (ticketId: string, cachedOnly = true) =>
    afetch(`${ENGINE}/satellite/check`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket_id: ticketId, cached_only: cachedOnly }) }).then((r) => json<Evidence>(r)),
  tickets: (city?: string, status?: string, limit = 100, sort: "newest" | "risk" = "newest") => {
    const q = new URLSearchParams({ limit: String(limit), sort });
    if (city) q.set("city", city);
    if (status) q.set("status", status);
    return afetch(`${ENGINE}/tickets?${q}`).then((r) => json<TicketWithScore[]>(r));
  },
  cities: () => afetch(`${ENGINE}/cities`).then((r) => json<CitySummary[]>(r)),
  ticket: (id: string) => afetch(`${ENGINE}/tickets/${id}`).then((r) => json<Ticket>(r)),
  score: (id: string) => afetch(`${ENGINE}/tickets/${id}/score`).then((r) => json<Score>(r)),
  wardStats: (city?: string) =>
    afetch(`${ENGINE}/wards/stats${city ? `?city=${city}` : ""}`).then((r) => json<WardStat[]>(r)),
  startRun: (id: string) =>
    afetch(`${AGENT}/agent/run/${id}`, { method: "POST" }).then((r) => json<{ run_id: string }>(r)),
  approvals: (status?: string) =>
    afetch(`${AGENT}/approvals${status ? `?status=${status}` : ""}`).then((r) => json<Approval[]>(r)),
  decide: (id: string, decision: "approve" | "reject", note?: string) =>
    afetch(`${AGENT}/approvals/${id}/decide`, {
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
