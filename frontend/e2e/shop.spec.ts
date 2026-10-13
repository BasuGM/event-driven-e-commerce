import { expect, test } from "@playwright/test"

test("browse: category filter → search → product → offers", async ({ page }) => {
  // Uncaught errors (e.g. hydration mismatches) fail the smoke test even if the UI looks fine
  const pageErrors: string[] = []
  page.on("pageerror", (error) => pageErrors.push(error.message))

  await page.goto("/shop")
  await expect(page.getByRole("heading", { level: 1, name: "Shop" })).toBeVisible()
  await expect(page.getByText(/\d[\d,]* products/)).toBeVisible()

  // Category filter (desktop sidebar)
  await page.getByRole("complementary", { name: "Filters" }).getByRole("link", { name: /Bed Bath Table/ }).click()
  await expect(page).toHaveURL(/category=bed-bath-table/)
  await expect(page.getByRole("heading", { level: 1, name: "Bed Bath Table" })).toBeVisible()

  // Search for a word taken from the first result, so the test doesn't depend on generated names
  // Product cards link to /shop/<slug>; the sidebar's category links go to /shop?category=…
  const products = page.locator('main a[href^="/shop/"]')
  const firstName = (await products.first().innerText()).trim()
  const term = firstName.split(" ").at(-1)!.toLowerCase()
  const search = page.getByRole("searchbox", { name: "Search products" })
  // The dev server may still be hydrating the page on first visit; retry until the
  // (client-side) search box actually reacts and the URL picks up the query.
  await expect(async () => {
    await search.fill(term)
    await search.press("Enter")
    await expect(page).toHaveURL(new RegExp(`q=${term}`), { timeout: 5_000 })
  }).toPass({ timeout: 120_000 })
  await expect(page).toHaveURL(/category=bed-bath-table/)
  await expect(page.getByText(new RegExp(`products? for “${term}”`, "i"))).toBeVisible()

  // Open the first matching product
  const result = products.first()
  const name = (await result.innerText()).trim()
  await result.click()
  await expect(page).toHaveURL(/\/shop\/[a-z0-9-]+$/)
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible()

  // Offers table
  const offers = page.getByRole("table")
  await expect(offers.getByRole("columnheader", { name: "Seller" })).toBeVisible()
  await expect(offers.getByRole("row")).not.toHaveCount(1) // header + at least one offer
  await expect(offers.getByText(/R\$/).first()).toBeVisible()

  expect(pageErrors).toEqual([])
})
