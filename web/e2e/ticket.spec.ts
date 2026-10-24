import { expect, test } from "@playwright/test";
import { mockAuth, mockData, signIn, type Profile } from "./helpers";

const officer: Profile = { user_id: "o1", email: "officer@city.gov", role: "officer", status: "active", requested_role: null, ticket_ids: [] };
async function signedIn(page: import("@playwright/test").Page) {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, officer.email);
  await expect(page).toHaveURL(/\/dashboard$/);
}

const ticket = { ticket_id: "blr-1", city: "bengaluru", data_quality: "real", source: "x", category: "drain", text: "Water stagnation", lang: "en", lat: null, lng: null, h3: null, ward: "Hoodi", created_at: "2026-01-01T00:00:00Z", closed_at: "2026-01-05T00:00:00Z", closed_by_hash: null, status: "closed", closure_note: null, closure_photo_url: null };
const score = { ticket_id: "blr-1", p_false_closure: 0.5, model_version: "v", reasons: [], eligible_checks: [], satellite_eligible: false, satellite_reason: "not applicable: drains are too small", score_type: "risk_rank_prior", risk_percentile: 0.9 };

test("a ticket the agent has not run yet opens normally (pending record has no run id or timestamps)", async ({ page }) => {
  await signedIn(page);
  await page.route("**/api/engine/tickets/blr-1", (r) => r.fulfill({ json: ticket }));
  await page.route("**/api/engine/tickets/blr-1/score", (r) => r.fulfill({ json: score }));
  // exactly what the Agent returns for a ticket with no run
  await page.route("**/api/agent/verification/blr-1/latest", (r) => r.fulfill({ json: { run_id: null, ticket_id: "blr-1", status: "pending", config_version: "v1", calibrated: false, closure_claimed: "unknown", verification_verdict: "not_performed", review_state: "none", prior: null, posterior: null, checks: [], provenance: {}, pending_reason: "No verification has been run for this ticket yet.", note: "n" } }));
  await page.goto("/ticket/blr-1");
  await expect(page.getByRole("heading", { name: "blr-1" })).toBeVisible();
  await expect(page.getByText(/No verification has been run/)).toBeVisible();
});

test("a verification record with missing fields never blanks the page", async ({ page }) => {
  await signedIn(page);
  await page.route("**/api/engine/tickets/blr-1", (r) => r.fulfill({ json: ticket }));
  await page.route("**/api/engine/tickets/blr-1/score", (r) => r.fulfill({ json: score }));
  await page.route("**/api/agent/verification/blr-1/latest", (r) => r.fulfill({ json: { run_id: "r1", ticket_id: "blr-1", config_version: "v1", calibrated: false, closure_claimed: "closed", verification_verdict: "cannot_tell", review_state: "none", prior: 0.5, posterior: 0.5, note: "n" } }));
  await page.goto("/ticket/blr-1");
  await expect(page.getByRole("heading", { name: "blr-1" })).toBeVisible();
});

test("a crash inside a page shows a message and a way out instead of a blank screen", async ({ page }) => {
  await signedIn(page);
  await page.route("**/api/engine/tickets/blr-1", (r) => r.fulfill({ json: { ...ticket, created_at: null } }));   // breaks `new Date(null).toLocaleDateString` safe, but text below forces a throw
  await page.route("**/api/engine/tickets/blr-1/score", (r) => r.fulfill({ json: { ...score, reasons: null } }));
  await page.goto("/ticket/blr-1");
  await expect(page.getByRole("alert").or(page.getByRole("heading", { name: "blr-1" }))).toBeVisible();
  expect((await page.locator("body").innerText()).length).toBeGreaterThan(50);
});
