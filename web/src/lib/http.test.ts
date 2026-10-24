// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { ApiError, onUnauthorized, request, setTokenProvider, streamSse, userMessage } from "./http";

const BASE = "http://engine.test";

describe("request", () => {
  it("turns an HTML 200 (SPA fallback) into a typed non_json error instead of a SyntaxError", async () => {
    server.use(http.get(`${BASE}/health`, () => new HttpResponse("<!doctype html><html></html>", { headers: { "content-type": "text/html" } })));
    const err = (await request(BASE, "/health").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("non_json");
    expect(userMessage(err)).not.toMatch(/SyntaxError|JSON|port|8001/i);
  });

  it("reads the {error:{code,message}} envelope and the request id", async () => {
    server.use(http.get(`${BASE}/x`, () => HttpResponse.json({ error: { code: "forbidden", message: "Not for you" }, request_id: "r1" }, { status: 403 })));
    const err = (await request(BASE, "/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toMatchObject({ kind: "forbidden", status: 403, code: "forbidden", message: "Not for you", requestId: "r1" });
  });

  it("maps a refused connection to a network error with plain wording", async () => {
    server.use(http.get(`${BASE}/down`, () => HttpResponse.error()));
    const err = (await request(BASE, "/down").catch((e: unknown) => e)) as ApiError;
    expect(err.kind).toBe("network");
    expect(userMessage(err)).toBe("This part of TrueClose is not responding right now. Try again in a moment.");
  });

  it("sends the bearer token and announces 401s that carried one", async () => {
    setTokenProvider(async () => "tok");
    const seen: string[] = [];
    server.use(http.get(`${BASE}/me`, ({ request: r }) => { seen.push(r.headers.get("authorization") ?? ""); return HttpResponse.json({ error: { code: "unauthorized", message: "expired" } }, { status: 401 }); }));
    const spy = vi.fn();
    const off = onUnauthorized(spy);
    await request(BASE, "/me").catch(() => undefined);
    off();
    expect(seen).toEqual(["Bearer tok"]);
    expect(spy).toHaveBeenCalledTimes(1);
    setTokenProvider(async () => null);
  });

  it("does not announce a 401 when no token was sent", async () => {
    setTokenProvider(async () => null);
    server.use(http.get(`${BASE}/me`, () => HttpResponse.json({ error: { code: "unauthorized", message: "no" } }, { status: 401 })));
    const spy = vi.fn();
    const off = onUnauthorized(spy);
    await request(BASE, "/me").catch(() => undefined);
    off();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("streamSse", () => {
  it("parses named events and stops at the end marker", async () => {
    const body = 'event: trace\ndata: {"step":1,"summary":"a"}\n\nevent: trace\ndata: {"step":2,"summary":"b"}\n\nevent: end\ndata: {}\n\n';
    server.use(http.get(`${BASE}/stream`, () => new HttpResponse(body, { headers: { "content-type": "text/event-stream" } })));
    const events: unknown[] = [];
    await new Promise<void>((resolve) => { streamSse(BASE, "/stream", (name, data) => { if (name === "trace") events.push(data); }, () => resolve()); });
    expect(events).toEqual([{ step: 1, summary: "a" }, { step: 2, summary: "b" }]);
  });

  it("reports a failed stream with the typed error", async () => {
    server.use(http.get(`${BASE}/stream`, () => HttpResponse.json({ error: { code: "forbidden", message: "no" } }, { status: 403 })));
    const err = await new Promise<ApiError | undefined>((resolve) => { streamSse(BASE, "/stream", () => undefined, resolve); });
    expect(err?.kind).toBe("forbidden");
  });
});
