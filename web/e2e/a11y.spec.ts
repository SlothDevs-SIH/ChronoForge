import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockAuth, mockData, signIn, type Profile } from "./helpers";

const officer: Profile = { user_id: "o1", email: "officer@city.gov", role: "officer", status: "active", requested_role: null, ticket_ids: [] };

async function scan(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
}

for (const path of ["/", "/how-it-works", "/auth/login", "/auth/register", "/auth/forgot-password", "/auth/official"]) {
  test(`axe finds no WCAG A/AA violations on ${path}`, async ({ page }) => {
    await mockData(page);
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await scan(page);
  });
}

test("axe finds no violations on the evaluation page", async ({ page }) => {
  await page.route("**/api/engine/eval/results", (r) => r.fulfill({ json: { is_placeholder: false } }));
  await page.goto("/evaluation");
  await page.waitForLoadState("networkidle");
  await scan(page);
});

test("axe finds no violations on the signed-in overview and triage queue", async ({ page }) => {
  await mockAuth(page, officer); await mockData(page);
  await page.goto("/auth/login");
  await signIn(page, officer.email);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.waitForLoadState("networkidle");
  await scan(page);
  await page.goto("/triage");
  await page.waitForLoadState("networkidle");
  await scan(page);
});

test("the how-it-works dock can be used with the keyboard alone", async ({ page }) => {
  await page.goto("/how-it-works");
  await page.getByRole("button", { name: /A complaint is marked resolved/ }).focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Risk assessment" })).toBeVisible();
  await page.getByRole("button", { name: /Try the evaluation/ }).click();
  await expect(page.getByRole("heading", { name: "Try the evaluation" })).toBeVisible();
});
