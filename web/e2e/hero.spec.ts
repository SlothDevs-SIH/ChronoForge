import { expect, test } from "@playwright/test";

const WIDTHS: [number, number][] = [[320, 640], [480, 800], [648, 900], [768, 1024], [1024, 768], [1440, 900], [720, 800]];   // the last is a half-screen window

for (const [w, h] of WIDTHS) {
  test(`hero at ${w}x${h}: no horizontal overflow, headline and the one action visible`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Closed should mean");
    await expect(page.getByRole("link", { name: "Open the dashboard" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    // the headline must not be clipped by the viewport edge
    const box = await page.getByRole("heading", { level: 1 }).boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(w + 1);
  });
}

for (const [w, h] of [[1024, 768], [1280, 720], [1440, 900]] as [number, number][]) {
  test(`hero at ${w}x${h} fits the screen without scrolling`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/");
    const extra = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
    expect(extra).toBeLessThanOrEqual(0);
  });
}

test("the video fills the hero and is muted, looping and inline", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const v = page.locator("video.hero-video");
  await expect(v).toHaveJSProperty("muted", true);
  await expect(v).toHaveJSProperty("loop", true);
  const b = await v.boundingBox();
  expect(Math.round(b!.width)).toBeGreaterThanOrEqual(1438);
  expect(Math.round(b!.height)).toBeGreaterThanOrEqual(898);
});

test("when the video cannot load, the poster stays and the pause control disappears", async ({ page }) => {
  await page.route("**/assets/hero/hero.*", (r) => r.abort());
  await page.goto("/");
  await expect(page.getByRole("button", { name: /background video/i })).toHaveCount(0);
  await expect(page.locator("video.hero-video")).toHaveAttribute("poster", "/assets/hero/hero-poster.jpg");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("reduced motion shows the poster and does not autoplay", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.locator("video.hero-video")).toHaveJSProperty("paused", true);
  await expect(page.getByRole("button", { name: "Play background video" })).toBeVisible();
  await ctx.close();
});

test("the pause control toggles playback", async ({ page }) => {
  await page.goto("/");
  const pause = page.getByRole("button", { name: "Pause background video" });
  await pause.click();
  await expect(page.locator("video.hero-video")).toHaveJSProperty("paused", true);
  await expect(page.getByRole("button", { name: "Play background video" })).toBeVisible();
});

test("the footer links reach the other public pages and nothing in the header repeats them", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header a")).toHaveCount(1);
  await page.getByRole("navigation", { name: "More pages" }).getByRole("link", { name: "How it works" }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
});
