import { expect, test } from "@playwright/test"

import { ASYNC_TIMEOUT, emptyCart, logIn, placeOrder } from "./helpers"

const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025"

test("log in → add to cart → checkout → pay on the provider's page → approved + email", async ({ page, request }) => {
  const pageErrors: string[] = []
  page.on("pageerror", (error) => pageErrors.push(error.message))

  await logIn(page)
  await emptyCart(page)

  const orderId = await placeOrder(page)

  // Order page: held stock, then pay on the (fake) provider's hosted page
  const status = page.getByTestId("order-status")
  await expect(status).toHaveText("Awaiting payment")
  await expect(page.getByRole("timer")).toContainText("Stock held for")
  await page.getByRole("button", { name: /^Pay R\$/ }).click()

  await expect(page).toHaveURL((url) => url.pathname.startsWith("/api/fake-provider/pay/pi_"))
  await page.getByRole("radio", { name: "Succeed", exact: true }).check()
  await page.getByRole("button", { name: /^Pay R\$/ }).click()

  // Back on the order page; the webhook confirms asynchronously (Celery worker -> Django)
  await expect(page).toHaveURL((url) => url.pathname === `/orders/${orderId}`, { timeout: ASYNC_TIMEOUT })
  await expect(status).toHaveText("Approved", { timeout: ASYNC_TIMEOUT })
  await expect(page.getByText("Payment received")).toBeVisible()

  // Exactly one confirmation email (consumer -> sender -> Mailpit)
  const subject = `Payment confirmed for order #${orderId.slice(0, 8)}`
  await expect
    .poll(
      async () => {
        const response = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `subject:"${subject}"` } })
        return (await response.json()).messages_count
      },
      { timeout: ASYNC_TIMEOUT },
    )
    .toBe(1)

  // And it's listed under Orders
  await page.goto("/orders")
  await expect(page.getByRole("row").nth(1)).toContainText("Approved")

  expect(pageErrors).toEqual([])
})
