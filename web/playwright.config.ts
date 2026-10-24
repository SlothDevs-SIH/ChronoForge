import { defineConfig } from "@playwright/test";

// Runs against the Vite dev server. Auth is exercised with a mocked Supabase and mocked API routes inside each test,
// so the suite needs no backend. Uses the installed Chrome (`channel: "chrome"`), falling back to Playwright's Chromium.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5180", channel: process.env.PW_CHANNEL ?? "chrome", trace: "retain-on-failure" },
  webServer: {
    command: "npx vite --port 5180 --strictPort --host 127.0.0.1 --mode e2e",
    url: "http://127.0.0.1:5180",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
