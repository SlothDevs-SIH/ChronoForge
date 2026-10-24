import type { Page } from "@playwright/test";

const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");

/** A structurally valid but unsigned JWT: the app only reads it; the (mocked) services decide what it means. */
export function fakeJwt(sub = "user-1", email = "a@b.co"): string {
  return `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub, email, role: "authenticated", aud: "authenticated", exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;
}

export type Profile = { user_id: string; email: string; role: "citizen" | "officer" | "admin"; status: "active" | "pending" | "rejected"; requested_role: string | null; ticket_ids: string[] };

/** Mocks Supabase's password sign-in and the Agent's /auth/me. Nothing leaves the machine. */
export async function mockAuth(page: Page, profile: Profile) {
  const user = { id: profile.user_id, aud: "authenticated", role: "authenticated", email: profile.email, user_metadata: {}, app_metadata: {}, created_at: new Date().toISOString() };
  const session = () => ({ access_token: fakeJwt(profile.user_id, profile.email), token_type: "bearer", expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, refresh_token: "refresh", user });
  await page.route("**/auth/v1/token**", (r) => r.fulfill({ json: session() }));
  await page.route("**/auth/v1/user**", (r) => r.fulfill({ json: user }));
  await page.route("**/auth/v1/logout**", (r) => r.fulfill({ status: 204, body: "" }));
  await page.route("**/api/agent/auth/me", (r) => r.fulfill({ json: profile }));
}

/** Empty but valid answers for the pages that load data, so a signed-in page renders without a backend. */
export async function mockData(page: Page) {
  await page.route("**/api/engine/tickets?**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/engine/wards/**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/engine/cities", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/engine/health", (r) => r.fulfill({ json: { ok: true, mode: "warehouse" } }));
  await page.route("**/api/agent/health", (r) => r.fulfill({ json: { ok: true, stubs: false } }));
  await page.route("**/api/agent/approvals**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/agent/admin/users**", (r) => r.fulfill({ json: [] }));
}

export async function signIn(page: Page, email = "a@b.co", password = "long-enough-pass") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}
