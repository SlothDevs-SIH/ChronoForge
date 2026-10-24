// The API surface the pages use. All network access goes through lib/http.ts.
import { AGENT_BASE, ENGINE_BASE, request, streamSse } from "./lib/http";
import type {
  AdminUser, Approval, CasePhoto, Hotspot, SimilarRequest, Summary, TimelineEvent, AuditEntry, CitizenPhoto, CitySummary, Evidence, Me, ReplyInfo, Role, Score, Ticket, TicketWithScore,
  TraceEvent, VerificationRecord, WardDot, WardStat,
} from "./types";

const E = <T,>(path: string, opts?: Parameters<typeof request>[2]) => request<T>(ENGINE_BASE, path, opts);
const A = <T,>(path: string, opts?: Parameters<typeof request>[2]) => request<T>(AGENT_BASE, path, opts);

export const api = {
  // ---- Engine
  engineHealth: () => E<{ ok: boolean; mode: string }>("/health", { auth: false }),
  agentHealth: () => A<{ ok: boolean; stubs: boolean }>("/health", { auth: false }),
  cities: (windowDays?: number) => E<CitySummary[]>(`/cities${windowDays ? `?window_days=${windowDays}` : ""}`, { auth: false }),
  evalResults: () => E<Record<string, unknown>>("/eval/results", { auth: false }),
  tickets: (city?: string, status?: string, limit = 100, sort: "newest" | "risk" = "newest", offset = 0, extra: Record<string, string> = {}) => {
    const q = new URLSearchParams({ limit: String(limit), sort, offset: String(offset), ...extra });
    if (city) q.set("city", city);
    if (status) q.set("status", status);
    return E<TicketWithScore[]>(`/tickets?${q}`);
  },
  ticket: (id: string) => E<Ticket>(`/tickets/${encodeURIComponent(id)}`),
  score: (id: string) => E<Score>(`/tickets/${encodeURIComponent(id)}/score`),
  wardStats: (city?: string, windowDays?: number) => {
    const q = new URLSearchParams();
    if (city) q.set("city", city);
    if (windowDays) q.set("window_days", String(windowDays));
    return E<WardStat[]>(`/wards/stats${q.size ? `?${q}` : ""}`);
  },
  wardMap: (city: string, windowDays?: number) => E<WardDot[]>(`/wards/map?city=${encodeURIComponent(city)}${windowDays ? `&window_days=${windowDays}` : ""}`),
  satelliteCheck: (ticketId: string, cachedOnly = true) =>
    E<Evidence>("/satellite/check", { method: "POST", body: { ticket_id: ticketId, cached_only: cachedOnly } }),
  /** Demo set photos, served by the Engine (open-licence images, see demo/photos/ATTRIBUTION.md). Public. */
  demoPhoto: (ticketId: string, which: "before" | "after") => `${ENGINE_BASE}/media/demo/${ticketId}/${which}.jpg`,
  /** Satellite chips are images, so the browser fetches them as blobs with the token (see useAuthedImage). */
  satelliteChipPath: (ticketId: string, which: "before" | "after") => `${ENGINE_BASE}/satellite/chip/${encodeURIComponent(ticketId)}/${which}.png`,

  // ---- Agent
  me: () => A<Me>("/auth/me"),
  setProfile: (requestedRole: "citizen" | "officer") => A<Me>("/auth/profile", { method: "POST", body: { requested_role: requestedRole } }),
  myTickets: () => A<{ ticket_id: string }[]>("/me/tickets"),
  adminUsers: (status?: string) => A<AdminUser[]>(`/admin/users${status ? `?status=${status}` : ""}`),
  approveUser: (id: string) => A<AdminUser>(`/admin/users/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  rejectUser: (id: string) => A<AdminUser>(`/admin/users/${encodeURIComponent(id)}/reject`, { method: "POST" }),
  setUserRole: (id: string, role: Role) => A<AdminUser>(`/admin/users/${encodeURIComponent(id)}/role`, { method: "POST", body: { role } }),
  linkTicket: (id: string, ticketId: string) => A<AdminUser>(`/admin/users/${encodeURIComponent(id)}/tickets`, { method: "POST", body: { ticket_id: ticketId } }),
  unlinkTicket: (id: string, ticketId: string) => A<AdminUser>(`/admin/users/${encodeURIComponent(id)}/tickets/${encodeURIComponent(ticketId)}`, { method: "DELETE" }),
  verification: (ticketId: string) => A<VerificationRecord>(`/verification/${encodeURIComponent(ticketId)}/latest`),
  startRun: (id: string) => A<{ run_id: string }>(`/agent/run/${encodeURIComponent(id)}`, { method: "POST" }),
  approvals: (status?: string) => A<Approval[]>(`/approvals${status ? `?status=${status}` : ""}`),
  decide: (id: string, decision: "approve" | "reject", note?: string) =>
    A<Approval>(`/approvals/${encodeURIComponent(id)}/decide`, { method: "POST", body: { decision, note } }),
  audit: () => A<AuditEntry[]>("/audit"),
  auditVerify: () => A<{ ok: boolean; first_broken_idx: number | null; length: number }>("/audit/verify"),
  replyLink: (ticketId: string, lang: string) => A<{ token: string; expires_at: string }>("/citizen/reply-links", { method: "POST", body: { ticket_id: ticketId, lang } }),
  ticketEvidence: (ticketId: string) => A<CitizenPhoto[]>(`/tickets/${encodeURIComponent(ticketId)}/evidence`),
  /** A short-lived signed link to one stored citizen photo. A relative link is served by the Agent itself. */
  evidenceUrl: async (evidenceId: string) => {
    const r = await A<{ url: string; expires_in: number }>(`/evidence/${encodeURIComponent(evidenceId)}/url`);
    return r.url.startsWith("/") ? `${AGENT_BASE}${r.url}` : r.url;
  },
  replyInfo: (token: string) => A<ReplyInfo>(`/reply/${encodeURIComponent(token)}`, { auth: false }),
  reply: (token: string, answer: "yes" | "partly" | "no", lang: string) =>
    A<{ ok: boolean }>(`/reply/${encodeURIComponent(token)}`, { method: "POST", body: { answer, lang }, auth: false }),

  // ---- website requests, case history and the features around them
  submitRequest: (body: { category: string; text: string; ward: string }) =>
    A<{ ticket: Ticket; telegram_link: string | null; linked: boolean }>("/me/requests", { method: "POST", body }),
  telegramLink: (id: string) => A<{ telegram_link: string | null; linked: boolean }>(`/me/requests/${encodeURIComponent(id)}/telegram-link`, { method: "POST" }),
  similar: (category: string, text: string, ward: string) => A<SimilarRequest[]>(`/me/requests/similar?${new URLSearchParams({ category, text, ward })}`),
  caseTimeline: (id: string) => A<TimelineEvent[]>(`/cases/${encodeURIComponent(id)}/timeline`),
  casePhotos: (id: string) => A<CasePhoto[]>(`/cases/${encodeURIComponent(id)}/photos`),
  summary: (days: number) => A<Summary>(`/admin/summary?days=${days}`),
  retryApproval: (id: string) => A<Approval>(`/approvals/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  closeRequest: (id: string) => A<{ ticket_id: string; status: string }>(`/admin/requests/${encodeURIComponent(id)}/close`, { method: "POST" }),
  hotspots: (windowDays?: number) => E<{ rule: string; caveat: string; hotspots: Hotspot[] }>(`/insights/hotspots${windowDays ? `?window_days=${windowDays}` : ""}`),

  /** Live agent trace. The Agent sends NAMED events (`trace`, `end`); the stream carries the Authorization header. */
  streamRun(runId: string, onEvent: (e: TraceEvent) => void, onEnd: (failed: boolean) => void): () => void {
    return streamSse(AGENT_BASE, `/agent/stream/${encodeURIComponent(runId)}`, (name, data) => {
      const e = data as TraceEvent;
      if ((name === "trace" || name === "message") && e && typeof e.step === "number") onEvent(e);
    }, (err) => onEnd(Boolean(err)));
  },
};
