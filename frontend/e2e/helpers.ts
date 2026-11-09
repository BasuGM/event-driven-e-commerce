import { expect, type Page } from "@playwright/test"

const EMAIL = process.env.E2E_USER_EMAIL ?? "customer@example.com"
const PASSWORD = process.env.E2E_USER_PASSWORD ?? "devpass123"
// Anything that waits on the Celery worker / consumers (webhooks, email, live updates)
export const ASYNC_TIMEOUT = 30_000

export async function logIn(page: Page, email = EMAIL, password = PASSWORD) {
  await page.goto("/login?next=/shop")
  // Retry until the (client) form is hydrated and the login goes through
  await expect(async () => {
    await page.getByLabel("Email").fill(email)
    await page.getByLabel("Password").fill(password)
    await page.getByRole("button", { name: "Log in" }).click()
    // Match the pathname, not the whole URL: /\/shop$/ would also match /login?next=/shop
    await expect(page).toHaveURL((url) => url.pathname === "/shop", { timeout: 5_000 })
  }).toPass({ timeout: 90_000 })
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
  const addButton = page.getByRole("button", { name: /^Add to cart/ }).first()
  await expect(async () => {
    await addButton.click()
    await expect(page.getByRole("status").filter({ hasText: "Added to cart" })).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 60_000 })
  await expect(page.getByRole("link", { name: /Cart, 1 item/ })).toBeVisible()

  await page.goto("/cart")
  await page.getByRole("link", { name: "Checkout" }).click()
  await expect(page).toHaveURL((url) => url.pathname === "/checkout")
  await page.getByLabel("Street and number").fill("Av. Paulista, 1000")
  await page.getByLabel("City").fill("São Paulo")
  await page.getByRole("combobox", { name: "State" }).click()
  await page.getByRole("option", { name: "SP", exact: true }).click()
  await page.getByLabel("CEP").fill("01310100")
  await expect(page.getByLabel("CEP")).toHaveValue("01310-100")
  await page.getByRole("button", { name: "Place order" }).click()

  await expect(page).toHaveURL((url) => /^\/orders\/[0-9a-f]{32}$/.test(url.pathname), { timeout: 30_000 })
  return new URL(page.url()).pathname.split("/").at(-1)!
}
