import { defineConfig, devices } from "@playwright/test"

/**
 * Smoke tests against the running dev stack (run via `make e2e`, inside the Playwright Docker
 * image). Timeouts are generous because the Next dev server compiles routes on first visit.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  retries: 0,
  // The specs share one customer account (and its cart): run them one at a time
  workers: 1,
  reporter: [["list"]],
  outputDir: "/tmp/playwright-results",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    navigationTimeout: 150_000,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
})
