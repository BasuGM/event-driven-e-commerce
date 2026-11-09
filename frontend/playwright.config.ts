import { defineConfig, devices } from "@playwright/test"

/**
 * Smoke tests, run by `make e2e` inside the Playwright Docker image against the isolated e2e
 * stack (scripts/e2e.sh). Timeouts are generous because the Next dev server compiles routes on
 * first visit.
 *
 * Results: PLAYWRIGHT_OUTPUT_DIR / PLAYWRIGHT_REPORT_DIR point at the host-mounted, gitignored
 * e2e-results/ folder in compose, so traces, videos and the HTML report of a failed run survive
 * the --rm container. Outside compose they fall back to /tmp.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  retries: 0,
  // The specs share one customer account (and its cart): run them one at a time
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: process.env.PLAYWRIGHT_REPORT_DIR ?? "/tmp/playwright-report", open: "never" }],
  ],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? "/tmp/playwright-results",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    navigationTimeout: 150_000,
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
})
