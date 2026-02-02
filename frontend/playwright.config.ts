import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const workers = (() => {
  const raw = (process.env.PW_WORKERS ?? "").trim();
  if (!raw) return 1; // Integration tests share one backend DB; run serial by default.
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 1;
})();

export default defineConfig({
  testDir: "./e2e",
  outputDir: "../output/playwright",
  workers,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
