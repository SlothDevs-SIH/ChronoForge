import { expect, test } from "@playwright/test";
import { mockAuth, mockData, signIn, type Profile } from "./helpers";

const officer: Profile = { user_id: "o1", email: "officer@city.gov", role: "officer", status: "active", requested_role: null, ticket_ids: [] };
const admin: Profile = { ...officer, user_id: "a1", email: "admin@team.dev", role: "admin" };
const citizen: Profile = { ...officer, user_id: "c1", email: "citizen@home.in", role: "citizen", ticket_ids: ["BLR-1"] };
const pending: Profile = { ...officer, user_id: "p1", status: "pending", requested_role: "officer" };

test("a signed-out visitor is sent to login and brought back after signing in", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/approvals");
  await expect(page).toHaveURL(/\/auth\/login\?next=%2Fapprovals/);
  await signIn(page, officer.email);
  await expect(page).toHaveURL(/\/approvals$/);
  await expect(page.getByRole("heading", { name: "Approval queue" })).toBeVisible();
});

test("an officer lands on the dashboard and sees staff navigation but no admin link", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, officer.email);
  await expect(page).toHaveURL(/\/dashboard$/);
  const nav = page.getByRole("navigation", { name: "Application" });
  await expect(nav.getByRole("link", { name: "Triage queue" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Admin" })).toHaveCount(0);
});

test("an officer who opens the admin page gets the 403 page", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, officer.email);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: /don't have access/i })).toBeVisible();
});

test("an admin reaches the admin page", async ({ page }) => {
  await mockAuth(page, admin); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, admin.email);
  await page.getByRole("navigation", { name: "Application" }).getByRole("link", { name: "Admin" }).click();
  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
});

test("a citizen lands on their tickets and is redirected away from staff pages", async ({ page }) => {
  await mockAuth(page, citizen); await mockData(page);
  await page.route("**/api/engine/tickets/BLR-1", (r) => r.fulfill({ json: { ticket_id: "BLR-1", city: "bengaluru", data_quality: "real", source: "x", category: "pothole", text: "Pothole near the market", lang: "en", lat: null, lng: null, h3: null, ward: "Hoodi", created_at: "2026-01-01T00:00:00Z", closed_at: "2026-01-05T00:00:00Z", closed_by_hash: null, status: "closed", closure_note: null, closure_photo_url: null } }));
  await page.goto("/auth/login");
  await signIn(page, citizen.email);
  await expect(page).toHaveURL(/\/my-tickets$/);
  await expect(page.getByRole("heading", { name: "BLR-1" })).toBeVisible();
  await page.goto("/triage");
  await expect(page).toHaveURL(/\/my-tickets$/);
});

test("a pending officer sees the waiting screen and cannot open the dashboard", async ({ page }) => {
  await mockAuth(page, pending); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, pending.email);
  await expect(page).toHaveURL(/\/auth\/pending$/);
  await expect(page.getByRole("heading", { name: "Waiting for approval" })).toBeVisible();
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/auth\/pending$/);
});

test("when a service answers 401 the session ends and login explains why", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, officer.email);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.route("**/api/agent/approvals**", (r) => r.fulfill({ status: 401, json: { error: { code: "unauthorized", message: "expired" }, request_id: "x" } }));
  await page.getByRole("navigation", { name: "Application" }).getByRole("link", { name: "Approvals" }).click();
  await expect(page).toHaveURL(/\/auth\/login/);
  await expect(page.locator(".auth-note")).toContainText(/session ended/i);
});

test("a wrong password shows the message beside the field", async ({ page }) => {
  await page.route("**/auth/v1/token**", (r) => r.fulfill({ status: 400, json: { error: "invalid_grant", error_description: "Invalid login credentials" } }));
  await page.goto("/auth/login");
  await signIn(page, "x@y.zz", "wrong-password");
  await expect(page.getByRole("alert")).toContainText(/don't match/);
});

test("the official sign-in has no sign-up and the citizen sign-in offers both routes", async ({ page }) => {
  await page.goto("/auth/official");
  await expect(page.getByRole("heading", { name: "Official sign-in" })).toBeVisible();
  await expect(page.getByRole("link", { name: /create an account/i })).toHaveCount(0);
  await page.goto("/auth/login");
  await expect(page.getByRole("link", { name: /create an account/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /official sign-in/i })).toBeVisible();
});

test("unknown routes show the 404 page", async ({ page }) => {
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { name: /doesn't exist/i })).toBeVisible();
});

test("the keyboard can reach and submit the login form", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await page.getByLabel("Email").focus();
  await page.keyboard.type(officer.email);
  await page.keyboard.press("Tab");
  await page.keyboard.type("long-enough-pass");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/dashboard$/);
});
