// Mirrors the JSON contract in /contract. Keep in sync with contract/README.md.
export type City = "bengaluru" | "pune" | "mumbai" | "synthetic" | "demo" | "web";

export interface Ticket {
  ticket_id: string;
  city: City;
  data_quality: "real" | "partial" | "synthetic";
  source: string;
  category: string;
  text: string;
  lang: string;
  // Bengaluru has no exact point: ward centroid (location_precision "ward_centroid") or null; h3 is null there.
  lat: number | null;
  lng: number | null;
  h3: string | null;
  location_precision?: "exact" | "generated" | "ward_centroid" | "none" | null;
  ward: string;
  created_at: string;
  closed_at: string | null;
  closed_by_hash: string | null;
  status: "open" | "closed" | "reopened";
  closure_note: string | null;
  closure_photo_url: string | null;
  complaint_photo_url?: string | null;   // only the demo photo set (the "before" photo)
}

export interface Reason { feature: string; value: number | string | null; shap: number | null }
export interface Score {
  ticket_id: string;
  p_false_closure: number;
  model_version: string;
  reasons: Reason[];
  eligible_checks: string[];
  satellite_eligible: boolean;
  // Why the satellite check applies, or "not applicable: ..." for small problems (potholes, single garbage piles). Show it when false.
  satellite_reason?: string | null;
  // calibrated_probability: synthetic cities only. risk_rank_prior (Bengaluru) and rule_flags (Mumbai) are bounded
  // priors, NOT probabilities. baseline: no model applies. Show the type next to any score.
  score_type: "baseline" | "risk_rank_prior" | "rule_flags" | "calibrated_probability";
  risk_percentile?: number | null;
  flags?: string[];
}
export interface TicketWithScore { ticket: Ticket; score: Score }

/** A photo a citizen sent for review. Stored only; it carries no likelihood ratio. */
export interface CitizenPhoto {
  evidence_id: string;
  sha256: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Evidence {
  evidence_id: string;
  ticket_id: string;
  check: "photo" | "satellite" | "citizen" | "human";
  verdict: "supports_fix" | "contradicts_fix" | "inconclusive";
  likelihood_ratio: number;
  confidence: number;
  cost: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Verdict {
  ticket_id: string;
  state: "verified_fixed" | "likely_not_fixed" | "cannot_tell";
  prior: number;
  posterior: number;
  evidence_ids: string[];
  recommended_action: "none" | "ask_citizen" | "reopen" | "escalate" | "human_spot_check";
  requires_human: boolean;
  explanation: string;
}

export interface TraceEvent {
  run_id: string;
  step: number;
  type: "thought" | "tool_call" | "tool_result" | "verdict" | "approval_needed";
  tool: string | null;
  summary: string;
  cost_spent: number;
  budget_left: number;
  ts: string;
}

export interface WardStat {
  city: City; ward: string; category: string; tickets: number;
  closed?: number; reopened?: number; open?: number;
  official_rate: number;
  reopen_rate?: number | null;
  honest_rate: number | null; // null until the scorer exists
}

export interface CitySummary {
  city: City; tickets: number; closed: number; reopened: number; open: number;
  data_quality: "real" | "partial" | "synthetic";
  location_precision: "exact" | "generated" | "ward_centroid" | "none" | null;
  /** Span of the loaded data for this city (the counts above follow the requested window). */
  data_from?: string | null;
  data_as_of?: string | null;
}

export interface Approval {
  approval_id: string;
  ticket_id: string;
  action: "reopen" | "escalate";
  verdict_snapshot: Verdict;
  status: "pending" | "approved" | "rejected";
  note: string | null;
  engine_result?: { ok: boolean; error?: string } | null;
  actor_email?: string | null;
  explain?: { summary: string; against: string[]; for: string[]; unknown: string[] };
}

export interface TimelineEvent { ts: string; kind: string; text: string; audience: "citizen" | "staff" }
export interface CasePhoto { photo_id: string; received_at: string; data_url: string; details: { flags?: string[]; has_gps?: boolean; distance_m?: number } }
export interface SimilarRequest { ward: string; status: string; similarity: number; created_at: string }
export interface Summary { days: number; counts: Record<string, number>; labels: Record<string, string>; not_fixed_rate: number | null; pending_approvals: number; messages: { pending: number; sent: number; failed: number }; text: string }
export interface Hotspot { city: string; kind: "ward" | "closer"; key: string; closed: number; reopened: number; rate: number; city_rate: number; ratio: number; p_value: number }

export interface AuditEntry {
  idx: number; ts: string; prev_hash: string; hash: string;
  event: { type?: string; ticket_id?: string; run_id?: string; [key: string]: unknown };
}

export interface WardDot { ward: string; lat: number; lng: number; tickets: number; official_rate: number; reopen_rate: number | null }

// ---- Auth, roles and verification records (contract/AUTH_AND_DEPLOY.md) ----
export type Role = "citizen" | "officer" | "admin";
export type AccountStatus = "active" | "pending" | "rejected";
export interface Me {
  user_id: string; email: string; role: Role; status: AccountStatus;
  requested_role: string | null; ticket_ids: string[];
}
export interface AdminUser {
  user_id: string; email: string; role: Role; status: AccountStatus; requested_role: string | null;
  ticket_ids?: string[]; created_at?: string;
}
export interface VerificationCheck {
  check: "photo" | "satellite" | "citizen" | "human";
  performed: boolean; skipped_reason: string | null;
  verdict: "supports_fix" | "contradicts_fix" | "inconclusive" | null;
  likelihood_ratio: number | null; cost: number | null;
}
export interface VerificationRecord {
  run_id: string | null; ticket_id: string; created_at?: string; status?: string;
  config_version: string; calibrated: boolean;
  closure_claimed: string;
  verification_verdict: "verified_fixed" | "likely_not_fixed" | "cannot_tell" | "not_performed" | "pending";
  review_state: "none" | "pending" | "approved" | "rejected";
  prior: number | null; posterior: number | null;
  checks: VerificationCheck[];
  provenance: { data_quality?: string; score_type?: string; city?: string };
  note: string;
  pending_reason?: string | null;
}
export interface ReplyInfo { ticket_id: string; category: string; ward: string; lang: string; status: "open" | "answered" | "expired" }
