import { expect, test } from "@playwright/test"

import { ASYNC_TIMEOUT, emptyCart, logIn, placeOrder } from "./helpers"

test("pay with a delayed webhook: 'Payment in progress' survives a reload, then Approved arrives live", async ({ page }) => {
  await logIn(page)
  await emptyCart(page)
  const orderId = await placeOrder(page)

  // Pay on the provider's page; the success webhook is delivered 10 s later
  await page.getByRole("button", { name: /^Pay R\$/ }).click()
  await expect(page).toHaveURL((url) => url.pathname.startsWith("/api/fake-provider/pay/pi_"))
  await page.getByRole("radio", { name: /deliver the webhook after a delay/ }).check()
  await page.getByRole("combobox", { name: "Delay" }).selectOption("10")
  await page.getByRole("button", { name: /^Pay R\$/ }).click()

  // Back on the order page: "processing" is stored server-side ...
  await expect(page).toHaveURL((url) => url.pathname === `/orders/${orderId}`, { timeout: ASYNC_TIMEOUT })
  const inProgress = page.getByRole("button", { name: "Payment in progress" })
  await expect(inProgress).toBeDisabled()
  await expect(page.getByText("Confirming your payment…")).toBeVisible()
  await expect(page.getByRole("button", { name: /^Pay R\$/ })).toHaveCount(0)

  // ... so it survives a reload
  await page.reload()
  await expect(inProgress).toBeDisabled()
  await expect(page.getByText("Confirming your payment…")).toBeVisible()

  // From here on, no reloads: count what the page fetches while it waits
  const streams: string[] = []
  const refreshes: string[] = []
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (url.pathname === `/api/orders/${orderId}/stream/`) streams.push(request.url())
    const isRsc = request.headers()["rsc"] === "1" || url.searchParams.has("_rsc")
    if (url.pathname === `/orders/${orderId}` && isRsc) refreshes.push(request.url())
  })

  await expect(page.getByTestId("order-status")).toHaveText("Approved", { timeout: ASYNC_TIMEOUT + 10_000 })
  await expect(page.getByText("Payment received")).toBeVisible()
  await expect(inProgress).toHaveCount(0)

  expect(streams.length).toBeGreaterThan(0) // the live connection (opened after the reload)
  // Approved arrived through a refresh triggered by the stream: at least one, and only one per
  // real change (2 s polling would have made ~5 during the 10 s delay)
  expect(refreshes.length).toBeGreaterThanOrEqual(1)
  expect(refreshes.length).toBeLessThanOrEqual(2)
})
