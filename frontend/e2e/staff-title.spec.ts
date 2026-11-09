import { expect, test } from "@playwright/test"

import { logIn } from "./helpers"

const NEUTRAL = "Olist Commerce"
const STAFF_PASSWORD = process.env.E2E_USER_PASSWORD ?? "devpass123"

test("the staff title holds through the dashboard's 10 s refresh and client navigation", async ({ page }) => {
  await logIn(page, "staff@example.com", STAFF_PASSWORD)

  // Count the dashboard's RSC refreshes so the check below is known to run after one
  let refreshes = 0
  page.on("request", (request) => {
    const url = new URL(request.url())
    const isRsc = request.headers()["rsc"] === "1" || url.searchParams.has("_rsc")
    if (url.pathname === "/staff/analytics" && isRsc) refreshes += 1
  })

  await page.goto("/staff/analytics")
  await expect(page.getByRole("heading", { name: "Analytics", level: 1 })).toBeVisible({ timeout: 60_000 })
  await expect(page).toHaveTitle(`Analytics · Staff · ${NEUTRAL}`)
  await expect.poll(() => refreshes, { timeout: 30_000 }).toBeGreaterThanOrEqual(1)
  await page.waitForTimeout(3_000) // let the refreshed payload (and its metadata) commit
  await expect(page).toHaveTitle(`Analytics · Staff · ${NEUTRAL}`)

  // Client-side navigation to another staff page (no timer there)
  await page.getByRole("navigation", { name: "Staff tools" }).getByRole("link", { name: "Health" }).click()
  await expect(page.getByRole("heading", { name: "Event health", level: 1 })).toBeVisible({ timeout: 60_000 })
  await page.waitForTimeout(3_000)
  await expect(page).toHaveTitle(`Event health · Staff · ${NEUTRAL}`)
})

test("a non-staff visitor only ever gets the neutral title", async ({ page }) => {
  await logIn(page)
  const response = await page.request.get("/staff/analytics")
  const html = await response.text()
  expect(html).not.toContain("· Staff ·")
  expect(html).toContain(`<title>${NEUTRAL}</title>`)
  // In the browser Next's not-found UI sets its own title; it just must never be a staff one
  await page.goto("/staff/analytics")
  await page.waitForTimeout(3_000)
  expect(await page.title()).not.toContain("Staff")
})
