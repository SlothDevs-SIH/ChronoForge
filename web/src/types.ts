// Mirrors the JSON contract in /contract. Keep in sync with contract/README.md.
export type City = "bengaluru" | "pune" | "mumbai" | "synthetic" | "demo";

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
}

export interface Approval {
  approval_id: string;
  ticket_id: string;
  action: "reopen" | "escalate";
  verdict_snapshot: Verdict;
  status: "pending" | "approved" | "rejected";
  note: string | null;
}

export interface AuditEntry {
  idx: number; ts: string; prev_hash: string; hash: string;
  event: { type?: string; ticket_id?: string; run_id?: string; [key: string]: unknown };
}

export interface WardDot { ward: string; lat: number; lng: number; tickets: number; official_rate: number; reopen_rate: number | null }
