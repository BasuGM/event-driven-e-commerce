import { expect, test, type Page } from "@playwright/test"

const EMAIL = process.env.E2E_USER_EMAIL ?? "customer@example.com"
const PASSWORD = process.env.E2E_USER_PASSWORD ?? "devpass123"

async function logIn(page: Page) {
  await page.goto("/login?next=/shop")
  // Retry until the (client) form is hydrated and the login goes through
  await expect(async () => {
    await page.getByLabel("Email").fill(EMAIL)
    await page.getByLabel("Password").fill(PASSWORD)
    await page.getByRole("button", { name: "Log in" }).click()
    await expect(page).toHaveURL(/\/shop$/, { timeout: 5_000 })
  }).toPass({ timeout: 90_000 })
  await expect(page.getByRole("button", { name: /Account menu/ })).toBeVisible()
}

async function emptyCart(page: Page) {
  await page.goto("/cart")
  const remove = page.getByRole("button", { name: /^Remove / })
  while ((await remove.count()) > 0) {
    const before = await remove.count()
    await remove.first().click()
    await expect(remove).toHaveCount(before - 1, { timeout: 15_000 })
  }
  await expect(page.getByText("Your cart is empty")).toBeVisible()
}

test("log in → add to cart → checkout → simulate payment → approved", async ({ page }) => {
  const pageErrors: string[] = []
  page.on("pageerror", (error) => pageErrors.push(error.message))

  await logIn(page)
  await emptyCart(page)

  // A product with stock, first offer you can buy
  await page.goto("/shop?in_stock=true")
  await page.locator('main a[href^="/shop/"]').first().click()
  await expect(page).toHaveURL(/\/shop\/[a-z0-9-]+$/)
  const addButton = page.getByRole("button", { name: /^Add to cart/ }).first()
  await expect(async () => {
    await addButton.click()
    await expect(page.getByRole("status").filter({ hasText: "Added to cart" })).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 60_000 })
  await expect(page.getByRole("link", { name: /Cart, 1 item/ })).toBeVisible()

  // Cart → checkout
  await page.goto("/cart")
  await page.getByRole("link", { name: "Checkout" }).click()
  await expect(page).toHaveURL(/\/checkout$/)
  await page.getByLabel("Street and number").fill("Av. Paulista, 1000")
  await page.getByLabel("City").fill("São Paulo")
  await page.getByRole("combobox", { name: "State" }).click()
  await page.getByRole("option", { name: "SP", exact: true }).click()
  await page.getByLabel("CEP").fill("01310100")
  await expect(page.getByLabel("CEP")).toHaveValue("01310-100")
  await page.getByRole("button", { name: "Place order" }).click()

  // Order page: held stock, then simulated payment
  await expect(page).toHaveURL(/\/orders\/[0-9a-f]{32}$/, { timeout: 30_000 })
  const status = page.getByTestId("order-status")
  await expect(status).toHaveText("Awaiting payment")
  await expect(page.getByRole("timer")).toContainText("Stock held for")
  await page.getByRole("button", { name: "Simulate payment success" }).click()
  await expect(status).toHaveText("Approved", { timeout: 30_000 })
  await expect(page.getByText("Payment received")).toBeVisible()

  // And it's listed under Orders
  await page.goto("/orders")
  await expect(page.getByRole("row").nth(1)).toContainText("Approved")

  expect(pageErrors).toEqual([])
})
