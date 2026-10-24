import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Ticket } from "../types";

export interface TicketPhoto { src: string; alt: string; label: string }
type PhotoKind = "citizen" | "field" | "illustrative";
interface PhotoIndex { photos?: Record<string, { file: string; kind?: PhotoKind; alt?: string; credit?: string }> }

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

/**
 * The photo for a ticket's card, or null when none is known. Sources: the Engine's demo set (a real "as reported" photo
 * for DEMO-* tickets) and the folder index above. Nothing is generated and nothing is matched by category.
 */
export function useTicketPhoto(ticket: Pick<Ticket, "ticket_id" | "city" | "complaint_photo_url" | "category"> | undefined): TicketPhoto | null {
  const index = useQuery({ queryKey: ["ticket-photo-index"], queryFn: loadIndex, staleTime: Infinity, retry: false });
  if (!ticket) return null;
  if (ticket.city === "demo" && ticket.complaint_photo_url) {
    return { src: api.demoPhoto(ticket.ticket_id, "before"), alt: `${ticket.category.replace(/_/g, " ")} as reported on ${ticket.ticket_id}`, label: "Demo photo, open licence" };
  }
  const entry = index.data?.photos?.[ticket.ticket_id];
  if (!entry) return null;
  const kind = entry.kind ?? "illustrative";
  return { src: `/assets/ticket-photos/${entry.file}`, alt: entry.alt ?? `Photo for ${ticket.ticket_id}`, label: entry.credit ? `${KIND_LABEL[kind]}. ${entry.credit}` : KIND_LABEL[kind] };
}
