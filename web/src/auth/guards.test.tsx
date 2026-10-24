import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import type { Me } from "../types";
import { RequireAuth } from "./guards";
import { safeNext } from "./AuthPages";

const auth = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock("./AuthProvider", () => ({ useAuth: () => auth.value }));

const me = (over: Partial<Me> = {}): Me => ({ user_id: "u", email: "a@b.c", role: "officer", status: "active", requested_role: null, ticket_ids: [], ...over });
const Where = () => { const l = useLocation(); return <p data-testid="where">{l.pathname + l.search}</p>; };

function renderAt(path: string, roles?: ("citizen" | "officer" | "admin")[]) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard" element={<RequireAuth roles={roles}><p>secret dashboard</p></RequireAuth>} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => { auth.value = { status: "anonymous", me: null, profileError: null, sessionExpired: false }; });

  it("sends a signed-out visitor to login and remembers where they were going", () => {
    renderAt("/dashboard?city=pune");
    expect(screen.getByTestId("where")).toHaveTextContent("/auth/login?next=%2Fdashboard%3Fcity%3Dpune");
  });

  it("adds the expired flag when the session ended", () => {
    auth.value = { ...auth.value, sessionExpired: true };
    renderAt("/dashboard");
    expect(screen.getByTestId("where")).toHaveTextContent("expired=1");
  });

  it("shows a loading state while the session is being checked, never the page", () => {
    auth.value = { ...auth.value, status: "loading" };
    renderAt("/dashboard");
    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
  });

  it("explains when sign-in is not configured instead of showing the page", () => {
    auth.value = { ...auth.value, status: "unconfigured" };
    renderAt("/dashboard");
    expect(screen.getByRole("heading", { name: /sign-in isn't set up/i })).toBeInTheDocument();
  });

  it("sends a pending officer to the waiting screen", () => {
    auth.value = { ...auth.value, status: "authenticated", me: me({ status: "pending" }) };
    renderAt("/dashboard");
    expect(screen.getByTestId("where")).toHaveTextContent("/auth/pending");
  });

  it("lets an officer through", () => {
    auth.value = { ...auth.value, status: "authenticated", me: me() };
    renderAt("/dashboard", ["officer", "admin"]);
    expect(screen.getByText("secret dashboard")).toBeInTheDocument();
  });

  it("shows 403 to a signed-in user with the wrong role", () => {
    auth.value = { ...auth.value, status: "authenticated", me: me({ role: "officer" }) };
    renderAt("/dashboard", ["admin"]);
    expect(screen.getByRole("heading", { name: /don't have access/i })).toBeInTheDocument();
  });

  it("sends a citizen who opens a staff page to their own tickets", () => {
    auth.value = { ...auth.value, status: "authenticated", me: me({ role: "citizen" }) };
    renderAt("/dashboard", ["officer", "admin"]);
    expect(screen.getByTestId("where")).toHaveTextContent("/my-tickets");
  });

  it("does not show the page to a rejected account", () => {
    auth.value = { ...auth.value, status: "authenticated", me: me({ status: "rejected" }) };
    renderAt("/dashboard");
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /wasn't approved/i })).toBeInTheDocument();
  });
});

describe("safeNext", () => {
  it("only allows in-app paths, never other sites or the auth pages", () => {
    expect(safeNext("/dashboard?city=pune")).toBe("/dashboard?city=pune");
    expect(safeNext("//evil.example")).toBeNull();
    expect(safeNext("https://evil.example")).toBeNull();
    expect(safeNext("/auth/login")).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});
