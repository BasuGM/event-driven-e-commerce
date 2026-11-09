import { expect, test } from "@playwright/test"

import { ASYNC_TIMEOUT, emptyCart, logIn, placeOrder } from "./helpers"

test("pay with a delayed webhook: 'Payment in progress' survives a reload, then Approved arrives live", async ({ page }) => {
  await logIn(page)
  await emptyCart(page)
  const orderId = await placeOrder(page)

  // Pay on the provider's page; the success webhook is delivered 60 s later (10 s was flaky:
  // a slow dev-server render around the reload could use the whole window)
  await page.getByRole("button", { name: /^Pay R\$/ }).click()
  await expect(page).toHaveURL((url) => url.pathname.startsWith("/api/fake-provider/pay/pi_"))
  await page.getByRole("radio", { name: /deliver the webhook after a delay/ }).check()
  await page.getByRole("combobox", { name: "Delay" }).selectOption("60")
  await page.getByRole("button", { name: /^Pay R\$/ }).click()

  // Back on the order page: "processing" is stored server-side ...
  await expect(page).toHaveURL((url) => url.pathname === `/orders/${orderId}`, { timeout: ASYNC_TIMEOUT })
  const inProgress = page.getByRole("button", { name: "Payment in progress" })
  await expect(inProgress).toBeDisabled()
  await expect(page.getByText("Confirming your payment…")).toBeVisible()
  await expect(page.getByRole("button", { name: /^Pay R\$/ })).toHaveCount(0)

  // Count what the page fetches from the reload on (attached first: the EventSource can open
  // before the assertions below finish). The reload itself is a document request, not RSC.
  const streams: string[] = []
  const refreshes: string[] = []
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (url.pathname === `/api/orders/${orderId}/stream/`) streams.push(request.url())
    const isRsc = request.headers()["rsc"] === "1" || url.searchParams.has("_rsc")
    if (url.pathname === `/orders/${orderId}` && isRsc) refreshes.push(request.url())
  })

  // ... so it survives a reload
  await page.reload()
  await expect(inProgress).toBeDisabled()
  await expect(page.getByText("Confirming your payment…")).toBeVisible()

  await expect(page.getByTestId("order-status")).toHaveText("Approved", { timeout: ASYNC_TIMEOUT + 60_000 })
  await expect(page.getByText("Payment received")).toBeVisible()
  await expect(inProgress).toHaveCount(0)

  expect(streams.length).toBeGreaterThan(0) // the live connection (opened after the reload)
  // Approved arrived through a refresh triggered by the stream: at least one, and only one per
  // real change (2 s polling would have made dozens during the delay)
  expect(refreshes.length).toBeGreaterThanOrEqual(1)
  expect(refreshes.length).toBeLessThanOrEqual(2)
})
