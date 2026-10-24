import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTicketPhoto } from "../hooks/useTicketPhoto";
import type { Score, Ticket } from "../types";
import { CutoutActions, CutoutCard, CutoutContent, CutoutFooter, CutoutLabel, CutoutMedia, CutoutOverlay, CutoutPin } from "./CutoutCard";
import Icon from "./Icon";

type Tone = "forest" | "warning" | "danger" | "neutral";
export interface Pin { text: string; tone?: Tone }

const STATUS: Record<Ticket["status"], Pin> = {
  open: { text: "Open", tone: "warning" },
  closed: { text: "Closed", tone: "forest" },
  reopened: { text: "Reopened", tone: "danger" },
};

const label = (s: string) => s.replace(/_/g, " ");
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : null);

/** What a score pin says. Only synthetic cities have a probability; real cities show a rank or a flag. */
export function riskPin(s: Score | undefined): Pin | undefined {
  if (!s) return undefined;
  if (s.score_type === "calibrated_probability") return { text: `${Math.round(s.p_false_closure * 100)}% (synthetic)`, tone: s.p_false_closure >= 0.7 ? "danger" : "forest" };
  if (s.score_type === "risk_rank_prior") { const p = Math.round((s.risk_percentile ?? 0) * 100); return { text: `Risk rank ${p}`, tone: p >= 90 ? "danger" : "forest" }; }
  if (s.score_type === "rule_flags") return s.flags?.length ? { text: "Flagged", tone: "warning" } : { text: "No flag", tone: "neutral" };
  return { text: "Not scored", tone: "neutral" };
}

/**
 * One complaint as a cutout card. Everything shown comes from the ticket record. The photo comes from `useTicketPhoto`:
 * the demo set's own "as reported" photo, or an entry in public/assets/ticket-photos/index.json. Real Bengaluru and
 * Mumbai tickets have no photo in the source data, so they get an honest "no photo" panel, never a stock image.
 * `pin` overrides the status badge (the triage queue shows the risk signal there).
 */
export default function ComplaintCard({ ticket, to, actionLabel = "Review evidence", note, showSummary = true, pin }: {
  ticket: Ticket; to?: string; actionLabel?: string; note?: ReactNode; showSummary?: boolean; pin?: Pin;
}) {
  const photo = useTicketPhoto(ticket);
  const [broken, setBroken] = useState(false);
  const shown = photo && !broken ? photo : null;
  const badge = pin ?? STATUS[ticket.status];
  const closed = when(ticket.closed_at);
  const synthetic = ticket.data_quality === "synthetic" || ticket.city === "demo";
  return (
    <CutoutCard className="complaint-card">
      <CutoutMedia>
        {shown
          ? <img src={shown.src} alt={shown.alt} loading="lazy" title={shown.label} onError={() => setBroken(true)} />
          : <div className="cutout-empty"><Icon name="photo" size={30} /><span>{broken ? "Photo unavailable" : "No photo on file"}</span><small>{broken ? "The image could not be loaded" : "The city's record has no image for this ticket"}</small></div>}
        {shown && <CutoutOverlay />}
        <CutoutPin tone={badge.tone}>{badge.text}</CutoutPin>
        <CutoutLabel>{label(ticket.category)}</CutoutLabel>
        {shown && <span className="cutout-credit">{shown.label}</span>}
      </CutoutMedia>
      <CutoutContent>
        <h3 className="complaint-id">{ticket.ticket_id}</h3>
        {showSummary && <p className="cutout-clamp">{ticket.text}</p>}
        <p className="complaint-meta">{ticket.ward} · {ticket.city}{closed ? ` · closed ${closed}` : ""}</p>
      </CutoutContent>
      <CutoutFooter>
        <span className={`badge ${synthetic ? "synthetic" : "real"}`}>{synthetic ? (shown ? "Demo photo, synthetic ticket" : "Synthetic ticket") : `${ticket.data_quality} record`}</span>
        {note && <span className="complaint-note">{note}</span>}
      </CutoutFooter>
      {to && <CutoutActions><Link className="btn btn-primary btn-sm complaint-link" to={to}>{actionLabel}</Link></CutoutActions>}
    </CutoutCard>
  );
}
