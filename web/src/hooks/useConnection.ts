import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export type LinkState = "connecting" | "connected" | "offline" | "error";
export interface ServiceStatus { state: LinkState; detail: string }

function describe(q: { isPending: boolean; isError: boolean; error: unknown; data?: unknown }, ok: string): ServiceStatus {
  if (q.isPending) return { state: "connecting", detail: "Checking" };
  if (!q.isError) return { state: "connected", detail: ok };
  const message = String((q.error as Error)?.message ?? q.error);
  // fetch() rejects with a TypeError when nothing answers; the dev proxy answers 500/502/504 when the target is down.
  return /^(5\d\d)|Failed to fetch|NetworkError/i.test(message) ? { state: "offline", detail: "Not responding" } : { state: "error", detail: message };
}

/** Real health checks against both services, through the same proxy the pages use. */
export function useConnection() {
  const opts = { refetchInterval: 5000, retry: false, staleTime: 0 } as const;
  const engine = useQuery({ queryKey: ["health", "engine"], queryFn: api.engineHealth, ...opts });
  const agent = useQuery({ queryKey: ["health", "agent"], queryFn: api.agentHealth, ...opts });
  return {
    engine: describe(engine, engine.data ? (engine.data.mode === "warehouse" ? "Real tickets loaded" : `Mode: ${engine.data.mode}`) : ""),
    agent: describe(agent, agent.data?.stubs ? "Stub tools (no real evidence)" : "Live tools"),
    agentStubs: Boolean(agent.data?.stubs),
  };
}
