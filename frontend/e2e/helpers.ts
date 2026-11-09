import { expect, type Page } from "@playwright/test"

const EMAIL = process.env.E2E_USER_EMAIL ?? "customer@example.com"
const PASSWORD = process.env.E2E_USER_PASSWORD ?? "devpass123"
// Anything that waits on the Celery worker / consumers (webhooks, email, live updates)
export const ASYNC_TIMEOUT = 30_000

export async function logIn(page: Page, email = EMAIL, password = PASSWORD) {
  await page.goto("/login?next=/shop")
  // The submit is disabled until the form has hydrated (useHydrated): wait for that before
  // typing, so hydration can't reset the fields, then submit exactly once.
  const submit = page.getByRole("button", { name: "Log in" })
  await expect(submit).toBeEnabled({ timeout: 60_000 })
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(password)
  await submit.click()
  // A full page load follows a login. Match the pathname: /\/shop$/ would match /login?next=/shop
  await expect(page).toHaveURL((url) => url.pathname === "/shop", { timeout: 60_000 })
  // The header (root layout) is rendered with the new session
  await expect(page.getByRole("button", { name: /Account menu/ })).toBeVisible()
}

export async function emptyCart(page: Page) {
  await page.goto("/cart")
  const remove = page.getByRole("button", { name: /^Remove / })
  while ((await remove.count()) > 0) {
    const before = await remove.count()
    await remove.first().click()
    await expect(remove).toHaveCount(before - 1, { timeout: 15_000 })
  }
  await expect(page.getByText("Your cart is empty")).toBeVisible()
}

/** Add the first in-stock offer to the (empty) cart and place the order. Returns its id. */
export async function placeOrder(page: Page): Promise<string> {
  await page.goto("/shop?in_stock=true")
  await page.locator('main a[href^="/shop/"]').first().click()
  await expect(page).toHaveURL((url) => /^\/shop\/[a-z0-9-]+$/.test(url.pathname))
  // Enabled only once hydrated, and Playwright waits for that: one click, never a lost or double add
  await page.getByRole("button", { name: /^Add to cart/ }).first().click()
  await expect(page.getByRole("status").filter({ hasText: "Added to cart" })).toBeVisible()
  await expect(page.getByRole("link", { name: /Cart, 1 item/ })).toBeVisible()

  await page.goto("/cart")
  await page.getByRole("link", { name: "Checkout" }).click()
  await expect(page).toHaveURL((url) => url.pathname === "/checkout")
  // Hydrated before typing (the submit is disabled until then)
  await expect(page.getByRole("button", { name: "Place order" })).toBeEnabled({ timeout: 60_000 })
  await page.getByLabel("Street and number").fill("Av. Paulista, 1000")
  await page.getByLabel("City").fill("São Paulo")
  await page.getByRole("combobox", { name: "State" }).click()
  await page.getByRole("option", { name: "SP", exact: true }).click()
  await page.getByLabel("CEP").fill("01310100")
  await expect(page.getByLabel("CEP")).toHaveValue("01310-100")
  await page.getByRole("button", { name: "Place order" }).click()

  await expect(page).toHaveURL((url) => /^\/orders\/[0-9a-f]{32}$/.test(url.pathname), { timeout: 30_000 })
  // The header (root layout) must show the emptied cart on the order page: "Cart", not "Cart, 1 item"
  await expect(page.getByRole("link", { name: "Cart", exact: true })).toBeVisible()
  return new URL(page.url()).pathname.split("/").at(-1)!
}
