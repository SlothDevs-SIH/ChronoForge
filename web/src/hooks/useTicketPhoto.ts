import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Ticket } from "../types";

export interface TicketPhoto { src: string; alt: string; label: string; synthetic?: boolean }
type PhotoKind = "citizen" | "field" | "illustrative";
interface PhotoIndex {
  photos?: Record<string, { file: string; kind?: PhotoKind; alt?: string; credit?: string }>;
  /** A synthetic stand-in per complaint category, for tickets whose source data has no photo. */
  categories?: Record<string, { file: string; alt?: string }[]>;
}

const KIND_LABEL: Record<PhotoKind, string> = { citizen: "Citizen photo", field: "Site photo", illustrative: "Illustrative photo" };

/** public/assets/ticket-photos/index.json maps ticket ids to photos. A missing or malformed index just means no photos. */
async function loadIndex(): Promise<PhotoIndex> {
  try {
    const res = await fetch("/assets/ticket-photos/index.json", { headers: { Accept: "application/json" } });
    if (!res.ok || !(res.headers.get("content-type") ?? "").includes("json")) return {};
    return (await res.json()) as PhotoIndex;
  } catch {
    return {};
  }
}

const SYNTHETIC_LABEL = "Synthetic image, not a photo of this site";

/** A small stable number from the ticket id, so the same ticket always gets the same stand-in image. */
function pick(ticketId: string, count: number) {
  let h = 0;
  for (let i = 0; i < ticketId.length; i++) h = (h * 31 + ticketId.charCodeAt(i)) >>> 0;
  return h % count;
}

/**
 * The photo for a ticket's card, or null when none is known. Sources, in order: the Engine's demo set (a real "as reported"
 * photo for DEMO-* tickets), a per-ticket entry in the folder index, and last a synthetic stand-in for the ticket's
 * category. The stand-in is always labelled synthetic; it is never evidence and is not used on the verification panel.
 */
export function useTicketPhoto(ticket: Pick<Ticket, "ticket_id" | "city" | "complaint_photo_url" | "category"> | undefined): TicketPhoto | null {
  const index = useQuery({ queryKey: ["ticket-photo-index"], queryFn: loadIndex, staleTime: Infinity, retry: false });
  if (!ticket) return null;
  if (ticket.city === "demo" && ticket.complaint_photo_url) {
    return { src: api.demoPhoto(ticket.ticket_id, "before"), alt: `${ticket.category.replace(/_/g, " ")} as reported on ${ticket.ticket_id}`, label: "Demo photo, open licence" };
  }
  const entry = index.data?.photos?.[ticket.ticket_id];
  if (!entry) {
    const pool = index.data?.categories?.[ticket.category];
    if (!pool?.length) return null;
    const stand = pool[pick(ticket.ticket_id, pool.length)];
    return { src: `/assets/ticket-photos/${stand.file}`, alt: stand.alt ?? `Synthetic image for a ${ticket.category.replace(/_/g, " ")} complaint`, label: SYNTHETIC_LABEL, synthetic: true };
  }
  const kind = entry.kind ?? "illustrative";
  return { src: `/assets/ticket-photos/${entry.file}`, alt: entry.alt ?? `Photo for ${ticket.ticket_id}`, label: entry.credit ? `${KIND_LABEL[kind]}. ${entry.credit}` : KIND_LABEL[kind] };
}
