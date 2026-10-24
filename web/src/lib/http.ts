// The only place that calls fetch. Every response is checked for status AND content type, so a proxy or SPA fallback
// that answers with HTML becomes a typed error instead of a JSON SyntaxError shown to people.

/** Where the services live. Locally the Vite proxy answers on /api/*; in production set VITE_ENGINE_URL and VITE_AGENT_URL. */
const trim = (u: string) => u.replace(/\/+$/, "");
export const ENGINE_BASE = trim(import.meta.env.VITE_ENGINE_URL ?? "/api/engine");
export const AGENT_BASE = trim(import.meta.env.VITE_AGENT_URL ?? "/api/agent");

export type ApiErrorKind = "network" | "unauthorized" | "forbidden" | "not_found" | "non_json" | "server" | "client";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  constructor(kind: ApiErrorKind, status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

let tokenProvider: () => Promise<string | null> = async () => null;
const unauthorizedListeners = new Set<() => void>();

/** The auth layer registers how to get the current access token. */
export function setTokenProvider(fn: () => Promise<string | null>) { tokenProvider = fn; }
/** Called when a service answers 401 for a request that carried a token (an expired or revoked session). */
export function onUnauthorized(fn: () => void) { unauthorizedListeners.add(fn); return () => { unauthorizedListeners.delete(fn); }; }

const isJson = (res: Response) => (res.headers.get("content-type") ?? "").toLowerCase().includes("json");

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return status >= 500 ? "server" : "client";
}

async function toError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = `The request failed (${res.status}).`;
  let requestId = res.headers.get("x-request-id") ?? undefined;
  if (isJson(res)) {
    try {
      const body = await res.json();
      const env = body?.error;
      if (env && typeof env === "object") { code = String(env.code ?? code); message = String(env.message ?? message); }
      else if (typeof body?.detail === "string") message = body.detail;
      requestId = body?.request_id ?? requestId;
    } catch { /* keep the generic message */ }
  }
  return new ApiError(kindFor(res.status), res.status, code, message, requestId);
}

export interface RequestOptions extends Omit<RequestInit, "body"> { body?: unknown; auth?: boolean; form?: FormData }

export async function request<T>(base: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, auth = true, form, headers, ...rest } = opts;
  const h = new Headers(headers);
  const token = auth ? await tokenProvider() : null;
  if (token) h.set("Authorization", `Bearer ${token}`);
  let payload: BodyInit | undefined;
  if (form) payload = form;
  else if (body !== undefined) { h.set("Content-Type", "application/json"); payload = JSON.stringify(body); }
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...rest, headers: h, body: payload });
  } catch {
    throw new ApiError("network", 0, "network", "The service can't be reached right now. Check your connection and try again.");
  }
  if (!res.ok) {
    const err = await toError(res);
    if (err.kind === "unauthorized" && token) unauthorizedListeners.forEach((fn) => fn());
    throw err;
  }
  if (res.status === 204) return undefined as T;
  if (!isJson(res)) throw new ApiError("non_json", res.status, "non_json", "The service sent an unexpected response. It may be starting up or misconfigured.");
  try { return (await res.json()) as T; }
  catch { throw new ApiError("non_json", res.status, "bad_json", "The service sent a response that could not be read."); }
}

/** Plain-language text for any thrown value; never contains ports, paths or commands. */
export function userMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.kind === "network" || err.kind === "non_json") return "This part of TrueClose is not responding right now. Try again in a moment.";
    if (err.kind === "unauthorized") return "Your session has ended. Sign in again to continue.";
    if (err.kind === "forbidden") return "Your account doesn't have access to this.";
    if (err.kind === "not_found") return "We couldn't find that.";
    if (err.kind === "server") return "Something went wrong on our side. Try again in a moment.";
    return err.message;
  }
  return "Something went wrong. Try again.";
}

/**
 * Server-sent events over fetch, so the Authorization header can be sent (EventSource cannot).
 * Calls onEvent for each `data:` JSON object, onEnd when the stream finishes or fails. Returns an abort function.
 */
export function streamSse(base: string, path: string, onEvent: (name: string, data: unknown) => void, onEnd: (err?: ApiError) => void): () => void {
  const ctrl = new AbortController();
  void (async () => {
    try {
      const token = await tokenProvider();
      const res = await fetch(`${base}${path}`, { headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, signal: ctrl.signal });
      if (!res.ok) { onEnd(await toError(res)); return; }
      if (!res.body) { onEnd(new ApiError("non_json", res.status, "no_stream", "The service did not open a live stream.")); return; }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let cut: number;
        while ((cut = buf.search(/\r?\n\r?\n/)) >= 0) {
          const block = buf.slice(0, cut);
          buf = buf.slice(cut).replace(/^\r?\n\r?\n/, "");
          let name = "message";
          const data: string[] = [];
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith("event:")) name = line.slice(6).trim();
            else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
          }
          if (!data.length) continue;
          let parsed: unknown = data.join("\n");
          try { parsed = JSON.parse(parsed as string); } catch { /* keep text */ }
          onEvent(name, parsed);
          if (name === "end") { onEnd(); return; }
        }
      }
      onEnd();
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      onEnd(new ApiError("network", 0, "network", "The live stream was interrupted."));
    }
  })();
  return () => ctrl.abort();
}

/** Fetch a protected image with the bearer token and return an object URL (revoke it when done). */
export async function fetchBlobUrl(url: string): Promise<string> {
  const token = await tokenProvider();
  let res: Response;
  try { res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} }); }
  catch { throw new ApiError("network", 0, "network", "The image can't be loaded right now."); }
  if (!res.ok) throw await toError(res);
  return URL.createObjectURL(await res.blob());
}
