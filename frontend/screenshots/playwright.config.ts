import { defineConfig, devices } from "@playwright/test"

/**
 * README screenshots (`make screenshots`). NOT part of `make e2e`: that config's testDir is
 * ./e2e, this one's is this folder. It writes data (orders, payments, a replay), so it runs only
 * against the disposable lab stack (compose project ecommerce-e2e, scripts/screenshots.sh), and
 * refuses any other base URL.
 */
const LAB_BASE_URL = "http://frontend:3000"
if (process.env.BASE_URL !== LAB_BASE_URL) {
  throw new Error(
    `screenshots: refusing to run with BASE_URL=${process.env.BASE_URL ?? "(unset)"}; ` +
      `only the lab stack (${LAB_BASE_URL}, started by make lab-up) is allowed. Use make screenshots.`,
  )
}

export default defineConfig({
  testDir: ".",
  testMatch: "*.shots.ts",
  timeout: 15 * 60_000,
  expect: { timeout: 60_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? "/tmp/playwright-screenshots",
  use: { baseURL: LAB_BASE_URL, navigationTimeout: 150_000, locale: "en-US" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
